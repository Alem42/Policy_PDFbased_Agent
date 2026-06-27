import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.modules.auth.dependencies import get_optional_user
from app.modules.documents.repositories.catalogue import document_catalogue_repository
from app.modules.documents.schemas import (
    DocumentAssetRead,
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentSearchResultRead,
    DocumentVersionRead,
)
from app.modules.documents.service import get_document as get_document_record
from app.modules.documents.service import resolve_pdf

router = APIRouter(prefix="/documents", tags=["documents"])
OptionalUser = Annotated[dict | None, Depends(get_optional_user)]


def _include_restricted(user: dict | None) -> bool:
    return user is not None and user.get("role") == "admin"


@router.get("", response_model=list[DocumentSearchResultRead])
async def list_documents(
    user: OptionalUser,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DocumentSearchResultRead]:
    return await document_catalogue_repository.list_documents(
        limit=limit,
        include_restricted=_include_restricted(user),
    )


@router.get("/search", response_model=list[DocumentSearchResultRead])
async def search_documents(
    user: OptionalUser,
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DocumentSearchResultRead]:
    return await document_catalogue_repository.search_documents(
        q,
        limit=limit,
        include_restricted=_include_restricted(user),
    )


@router.get("/{document_id}", response_model=DocumentDetailRead)
async def get_document(
    document_id: UUID,
    user: OptionalUser,
) -> DocumentDetailRead:
    document = await document_catalogue_repository.get_detail(
        document_id,
        include_restricted=_include_restricted(user),
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkRead])
async def list_document_chunks(
    document_id: UUID,
    user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DocumentChunkRead]:
    chunks = await document_catalogue_repository.chunks(
        document_id,
        limit=limit,
        include_restricted=_include_restricted(user),
    )
    if chunks is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return chunks


@router.get("/{document_id}/versions", response_model=list[DocumentVersionRead])
async def list_document_versions(
    document_id: UUID,
    user: OptionalUser,
) -> list[DocumentVersionRead]:
    versions = await document_catalogue_repository.versions(
        document_id,
        include_restricted=_include_restricted(user),
    )
    if versions is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return versions


@router.get("/{document_id}/assets", response_model=list[DocumentAssetRead])
async def list_document_assets(
    document_id: UUID,
    user: OptionalUser,
) -> list[DocumentAssetRead]:
    assets = await document_catalogue_repository.assets(
        document_id,
        include_restricted=_include_restricted(user),
    )
    if assets is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return assets


@router.get("/{document_id}/file", response_class=FileResponse)
async def get_document_file(document_id: UUID, user: OptionalUser) -> FileResponse:
    include_restricted = _include_restricted(user)
    try:
        document, path = await asyncio.gather(
            asyncio.to_thread(
                get_document_record,
                str(document_id),
                include_restricted,
            ),
            asyncio.to_thread(
                resolve_pdf,
                str(document_id),
                include_restricted,
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document file not found") from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document["original_filename"],
    )
