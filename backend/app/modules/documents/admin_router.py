import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.modules.auth.dependencies import require_admin
from app.modules.documents.admin_schemas import (
    AdminDocumentCreateResponse,
    AdminDocumentMetadataUpdate,
    AdminWebImportRequest,
    AdminWebImportResponse,
    DocumentProcessingStatus,
    ProcessingStatus,
    WebGovernanceRead,
    WebGovernanceUpdate,
    WebLifecycleStatus,
)
from app.modules.documents.exceptions import DuplicateDocumentError
from app.modules.documents.processing_queue import document_processing_queue
from app.modules.documents.service import (
    delete_document as delete_document_record,
)
from app.modules.documents.service import (
    get_document_detail,
    mark_document_queued,
    prepare_full_rescan,
    prepare_reembed,
    process_document,
    reembed_and_mark,
    save_upload,
)
from app.modules.documents.service import (
    update_document_metadata as update_document_metadata_record,
)
from app.modules.documents.web_governance import web_governance_service
from app.modules.documents.web_import import (
    WebImportRequest,
    web_import_service,
)
from app.modules.web_search.contracts import WebSearchProviderError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/documents", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


def _processing_status(status_value: str) -> ProcessingStatus:
    return {
        "uploaded": ProcessingStatus.QUEUED,
        "ocr": ProcessingStatus.OCR,
        "parsed": ProcessingStatus.CHUNKING,
        "annotated": ProcessingStatus.EMBEDDING,
        "ready": ProcessingStatus.INDEXED,
        "failed": ProcessingStatus.FAILED,
    }.get(status_value, ProcessingStatus.QUEUED)


@router.post("", response_model=AdminDocumentCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    admin: AdminUser,
    title: Annotated[str | None, Form()] = None,
    source_organisation: Annotated[str | None, Form()] = None,
    policy_area: Annotated[str | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
    country_or_region: Annotated[str | None, Form()] = None,
    published_year: Annotated[int | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
    credibility_level: Annotated[str, Form()] = "unknown",
) -> AdminDocumentCreateResponse:
    try:
        clean_source_url = source_url.strip() if source_url and source_url.strip() else None
        row = await save_upload(
            file,
            source_url=clean_source_url,
            canonical_url=clean_source_url,
            imported_by=str(admin["id"]),
            imported_via="file_upload_admin",
        )
        document_id = row["id"]

        metadata = {
            "title": title,
            "source_organisation": source_organisation,
            "policy_area": policy_area,
            "source_url": source_url,
            "country_or_region": country_or_region,
            "published_year": published_year,
            "tags": tags,
            "credibility_level": credibility_level,
        }
        if any(value is not None for value in metadata.values()):
            row = update_document_metadata_record(document_id, metadata)

        # A shared FIFO queue gives all users three processing slots in total.
        # Saving the upload remains quick; extraction/embedding runs in workers.
        await document_processing_queue.enqueue(document_id, _run_process_document)
        logger.info("Document %s queued for background processing", document_id)

        return AdminDocumentCreateResponse(
            id=document_id,
            processing_status=_processing_status(row.get("status", "uploaded")),
        )
    except DuplicateDocumentError as exc:
        # 409 Conflict: identical content already in the library (L1 dedup).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_id": exc.existing_id,
                "existing_filename": exc.existing_filename,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_process_document(document_id: str) -> None:
    """Process one document inside a queue worker thread."""
    try:
        process_document(document_id)
    except Exception as exc:
        logger.error("Background processing failed for %s: %s", document_id, exc)


@router.post(
    "/import-url",
    response_model=AdminWebImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_web_document(
    payload: AdminWebImportRequest,
    admin: AdminUser,
) -> AdminWebImportResponse:
    """Fetch one public web page and add it to the shared document library."""
    url = payload.url.strip()
    title = payload.title.strip() if payload.title else None
    try:
        result = await web_import_service.import_page(
            WebImportRequest(
                url=url,
                title=title,
                imported_by=str(admin["id"]),
                imported_via="web_import_admin",
            )
        )
        return AdminWebImportResponse(
            id=result.document["id"],
            title=result.title,
            source_url=result.source_url,
            was_duplicate=result.was_duplicate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WebSearchProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/web-governance", response_model=list[WebGovernanceRead])
async def list_web_governance(
    _: AdminUser,
    lifecycle_status: WebLifecycleStatus | None = None,
    due_only: bool = False,
) -> list[WebGovernanceRead]:
    rows = await asyncio.to_thread(
        web_governance_service.list,
        lifecycle_status=lifecycle_status.value if lifecycle_status else None,
        due_only=due_only,
    )
    return [WebGovernanceRead(**row) for row in rows]


@router.patch("/{document_id}/web-governance", response_model=WebGovernanceRead)
async def update_web_governance(
    document_id: UUID,
    payload: WebGovernanceUpdate,
    _: AdminUser,
) -> WebGovernanceRead:
    try:
        values = payload.model_dump(exclude_unset=True)
        lifecycle = values.get("lifecycle_status")
        if lifecycle is not None:
            values["lifecycle_status"] = lifecycle.value
        await asyncio.to_thread(
            web_governance_service.update,
            str(document_id),
            **values,
        )
        rows = await asyncio.to_thread(web_governance_service.list)
        row = next(item for item in rows if str(item["document_id"]) == str(document_id))
        return WebGovernanceRead(**row)
    except (FileNotFoundError, StopIteration) as exc:
        raise HTTPException(status_code=404, detail="Web governance record not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rescan", status_code=status.HTTP_202_ACCEPTED)
async def rescan_documents(_: AdminUser) -> dict:
    """Queue a full-library rescan through the shared processing queue.

    Every document is flipped to 'queued' up front (so the library shows the
    same upload-style lifecycle per row), then reprocessed by the workers —
    the request returns immediately instead of blocking on the whole library.
    """
    try:
        logger.info("Full library rescan requested; queueing every document")
        document_ids = await asyncio.to_thread(prepare_full_rescan)
        for document_id in document_ids:
            await document_processing_queue.enqueue(document_id, _run_process_document)
        return {"rescanned": True, "queued": len(document_ids)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_reembed_document(document_id: str) -> None:
    """Re-embed one document inside a queue worker thread."""
    try:
        reembed_and_mark(document_id)
    except Exception as exc:
        logger.error("Background re-embed failed for %s: %s", document_id, exc)


@router.post("/reembed", status_code=status.HTTP_202_ACCEPTED)
async def reembed_documents(_: AdminUser) -> dict:
    """Re-embed existing chunks into the active model's table (after a model switch).

    Reuses stored chunks (no re-extract / re-chunk), so other models' vectors
    are preserved and switching back stays instant. Runs through the shared
    processing queue: every ready document flips to the embedding state
    immediately and returns to 'ready' as its job completes, so the library
    UI can watch the progress per row.
    """
    try:
        logger.info("Library re-embed requested; queueing per-document jobs")
        document_ids, model = await asyncio.to_thread(prepare_reembed)
        for document_id in document_ids:
            await document_processing_queue.enqueue(document_id, _run_reembed_document)
        return {"documents": len(document_ids), "model": model, "queued": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{document_id}/rescan", status_code=status.HTTP_202_ACCEPTED)
async def rescan_document(
    document_id: UUID,
    _: AdminUser,
) -> dict:
    """Reprocess ONE document (re-extract, re-chunk, re-metadata, re-embed active model)."""
    try:
        await asyncio.to_thread(get_document_detail, str(document_id), True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Same lifecycle as a fresh upload: queued -> extracting -> ... -> ready.
    await asyncio.to_thread(mark_document_queued, str(document_id))
    await document_processing_queue.enqueue(str(document_id), _run_process_document)
    logger.info("Single-document rescan queued: %s", document_id)
    return {"id": str(document_id), "processing_status": "queued"}


@router.patch("/{document_id}", response_model=AdminDocumentMetadataUpdate)
async def update_document_metadata(
    document_id: UUID,
    payload: AdminDocumentMetadataUpdate,
    _: AdminUser,
) -> AdminDocumentMetadataUpdate:
    try:
        await asyncio.to_thread(
            update_document_metadata_record,
            str(document_id),
            payload.model_dump(exclude_unset=True),
        )
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, _: AdminUser) -> None:
    try:
        await asyncio.to_thread(delete_document_record, str(document_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/processing-status", response_model=DocumentProcessingStatus)
async def get_processing_status(
    document_id: UUID,
    _: AdminUser,
) -> DocumentProcessingStatus:
    try:
        queue_state = document_processing_queue.state(str(document_id))
        row = await asyncio.to_thread(get_document_detail, str(document_id), True)
        raw_status = row.get("status", "uploaded")
        if queue_state and queue_state.status == "queued":
            processing_status = ProcessingStatus.QUEUED
            progress_percent = 0
            message = (
                f"Waiting for a processing slot (queue position {queue_state.position})"
                if queue_state.position
                else "Waiting for a processing slot"
            )
        elif queue_state and queue_state.status == "processing" and raw_status in {
            "uploaded",
            "ready",
        }:
            processing_status = ProcessingStatus.EXTRACTING
            progress_percent = 10
            message = "Extracting document"
        else:
            processing_status = _processing_status(raw_status)
            progress_percent = {
                ProcessingStatus.QUEUED: 0,
                ProcessingStatus.EXTRACTING: 10,
                ProcessingStatus.OCR: 25,
                ProcessingStatus.CHUNKING: 50,
                ProcessingStatus.EMBEDDING: 75,
                ProcessingStatus.INDEXED: 100,
                ProcessingStatus.FAILED: 100,
            }[processing_status]
            message = {
                ProcessingStatus.QUEUED: "Waiting for a processing slot",
                ProcessingStatus.EXTRACTING: "Extracting document",
                ProcessingStatus.OCR: "Running OCR",
                ProcessingStatus.CHUNKING: "Chunking document",
                ProcessingStatus.EMBEDDING: "Creating embeddings",
                ProcessingStatus.INDEXED: "Document indexed",
                ProcessingStatus.FAILED: row.get("error_message"),
            }[processing_status]
        return DocumentProcessingStatus(
            id=document_id,
            status=processing_status,
            progress_percent=progress_percent,
            message=message,
            error=row.get("error_message") if raw_status == "failed" else None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
