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
    DocumentProcessingStatus,
    ProcessingStatus,
)
from app.modules.documents.service import (
    delete_document as delete_document_record,
)
from app.modules.documents.service import (
    get_document_detail,
    process_document,
    rescan_library,
    save_upload,
)
from app.modules.documents.service import (
    update_document_metadata as update_document_metadata_record,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/documents", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


def _processing_status(status_value: str) -> ProcessingStatus:
    return {
        "uploaded": ProcessingStatus.QUEUED,
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


@router.post("/rescan")
async def rescan_documents(_: AdminUser) -> dict:
    try:
        logger.info("Rescan requested, running in thread pool")
        result = await asyncio.to_thread(rescan_library, reprocess_existing=True)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
