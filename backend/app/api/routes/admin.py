from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.schemas.admin import (
    AdminDocumentCreateResponse,
    AdminDocumentMetadataUpdate,
    DocumentProcessingStatus,
    ProcessingStatus,
)
from app.services.auth_service import require_admin
from app.services.document_service import (
    delete_document as delete_document_record,
)
from app.services.document_service import (
    get_document_detail,
    rescan_library,
    save_upload,
)
from app.services.document_service import (
    update_document_metadata as update_document_metadata_record,
)

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
            row = update_document_metadata_record(row["id"], metadata)
        return AdminDocumentCreateResponse(
            document_id=row["id"],
            processing_status=_processing_status(row.get("status", "ready")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rescan")
async def rescan_documents(_: AdminUser) -> dict:
    try:
        return rescan_library(reprocess_existing=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/{document_id}", response_model=AdminDocumentMetadataUpdate)
async def update_document_metadata(
    document_id: UUID,
    payload: AdminDocumentMetadataUpdate,
    _: AdminUser,
) -> AdminDocumentMetadataUpdate:
    try:
        update_document_metadata_record(str(document_id), payload.model_dump(exclude_unset=True))
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, _: AdminUser) -> None:
    try:
        delete_document_record(str(document_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/processing-status", response_model=DocumentProcessingStatus)
async def get_processing_status(
    document_id: UUID,
    _: AdminUser,
) -> DocumentProcessingStatus:
    try:
        row = get_document_detail(str(document_id), include_restricted=True)
        return DocumentProcessingStatus(
            document_id=document_id,
            status=_processing_status(row.get("status", "uploaded")),
            progress_percent=100 if row.get("status") == "ready" else 50,
            message=row.get("error_message"),
            error=row.get("error_message") if row.get("status") == "failed" else None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
