from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.schemas.admin import (
    AdminDocumentCreateResponse,
    AdminDocumentMetadataUpdate,
    DocumentProcessingStatus,
)

router = APIRouter(prefix="/admin/documents", tags=["admin"])


@router.post("", response_model=AdminDocumentCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    source_organisation: Annotated[str, Form()],
    policy_area: Annotated[str, Form()],
    source_url: Annotated[str | None, Form()] = None,
    country_or_region: Annotated[str | None, Form()] = None,
    published_year: Annotated[int | None, Form()] = None,
    tags: Annotated[list[str] | None, Form()] = None,
    credibility_level: Annotated[str, Form()] = "unknown",
) -> AdminDocumentCreateResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Admin upload placeholder. Implement in feature/admin-upload.",
    )


@router.patch("/{document_id}", response_model=AdminDocumentMetadataUpdate)
async def update_document_metadata(
    document_id: UUID,
    payload: AdminDocumentMetadataUpdate,
) -> AdminDocumentMetadataUpdate:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Metadata editing placeholder. Implement in feature/admin-metadata.",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document deletion placeholder. Implement in feature/admin-metadata.",
    )


@router.get("/{document_id}/processing-status", response_model=DocumentProcessingStatus)
async def get_processing_status(document_id: UUID) -> DocumentProcessingStatus:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Processing status placeholder. Implement in feature/ingestion-pipeline.",
    )
