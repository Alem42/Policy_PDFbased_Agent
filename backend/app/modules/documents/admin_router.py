import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
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
from app.modules.documents.service import (
    delete_document as delete_document_record,
)
from app.modules.documents.service import (
    get_document_detail,
    process_document,
    reembed_library,
    rescan_library,
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
    background_tasks: BackgroundTasks,
    _: AdminUser,
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
        row = await save_upload(file)
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

        # Schedule heavy PDF processing in a thread pool so the response
        # returns immediately (202 Accepted) without blocking the event loop.
        background_tasks.add_task(_run_process_document, document_id)
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
    """Run process_document in a new thread via asyncio.to_thread wrapper.

    BackgroundTasks runs sync callables directly in a thread already, so this
    function is called in a worker thread and can safely block.
    """
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


@router.post("/rescan")
async def rescan_documents(_: AdminUser) -> dict:
    try:
        logger.info("Rescan requested, running in thread pool")
        result = await asyncio.to_thread(rescan_library, reprocess_existing=True)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/reembed")
async def reembed_documents(_: AdminUser) -> dict:
    """Re-embed existing chunks into the active model's table (after a model switch).

    Reuses stored chunks (no re-extract / re-chunk), so other models' vectors are
    preserved and switching back stays instant.
    """
    try:
        logger.info("Re-embed requested, running in thread pool")
        return await asyncio.to_thread(reembed_library)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{document_id}/rescan", status_code=status.HTTP_202_ACCEPTED)
async def rescan_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    _: AdminUser,
) -> dict:
    """Reprocess ONE document (re-extract, re-chunk, re-metadata, re-embed active model)."""
    background_tasks.add_task(_run_process_document, str(document_id))
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
        row = await asyncio.to_thread(get_document_detail, str(document_id), True)
        return DocumentProcessingStatus(
            id=document_id,
            status=_processing_status(row.get("status", "uploaded")),
            progress_percent=100 if row.get("status") == "ready" else 50,
            message=row.get("error_message"),
            error=row.get("error_message") if row.get("status") == "failed" else None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
