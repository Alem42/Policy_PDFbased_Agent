from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.document import DocumentAssetRead, DocumentRead, DocumentVersionRead
from app.services.document_repository import document_repository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    source_id: UUID | None = None,
) -> list[DocumentRead]:
    return await document_repository.list_documents(source_id)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID) -> DocumentRead:
    document = await document_repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/versions", response_model=list[DocumentVersionRead])
async def list_document_versions(document_id: UUID) -> list[DocumentVersionRead]:
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return await document_repository.versions(document_id)


@router.get("/{document_id}/assets", response_model=list[DocumentAssetRead])
async def list_document_assets(document_id: UUID) -> list[DocumentAssetRead]:
    if await document_repository.get(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return await document_repository.assets(document_id)
