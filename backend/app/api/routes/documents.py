from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.schemas.document import (
    DocumentAssetRead,
    DocumentDetailRead,
    DocumentSearchResultRead,
    DocumentSnippetRead,
    DocumentVersionRead,
)
from app.repositories.document_repository import document_repository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSearchResultRead])
async def list_documents(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DocumentSearchResultRead]:
    return await document_repository.list_documents(limit=limit)


@router.get("/search", response_model=list[DocumentSearchResultRead])
async def search_documents(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DocumentSearchResultRead]:
    return await document_repository.search_documents(q, limit=limit)


@router.get("/{document_id}", response_model=DocumentDetailRead)
async def get_document(
    document_id: UUID,
    snippet_limit: int = Query(default=8, ge=0, le=50),
) -> DocumentDetailRead:
    document = await document_repository.get_detail(
        document_id,
        snippet_limit=snippet_limit,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/chunks", response_model=list[DocumentSnippetRead])
async def list_document_chunks(
    document_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DocumentSnippetRead]:
    chunks = await document_repository.chunks(document_id, limit=limit)
    if chunks is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return chunks


@router.get("/{document_id}/versions", response_model=list[DocumentVersionRead])
async def list_document_versions(document_id: UUID) -> list[DocumentVersionRead]:
    versions = await document_repository.versions(document_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return versions


@router.get("/{document_id}/assets", response_model=list[DocumentAssetRead])
async def list_document_assets(document_id: UUID) -> list[DocumentAssetRead]:
    assets = await document_repository.assets(document_id)
    if assets is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return assets
