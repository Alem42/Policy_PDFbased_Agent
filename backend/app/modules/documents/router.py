import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.modules.auth.dependencies import get_optional_user
from app.modules.documents.file_store import document_file_store
from app.modules.documents.repositories.catalogue import document_catalogue_repository
from app.modules.documents.schemas import (
    DocumentAssetRead,
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentSearchPageRead,
    DocumentSearchResultRead,
    DocumentSort,
    DocumentStatus,
    DocumentVersionRead,
)
from app.modules.documents.service import get_document as get_document_record
from app.modules.documents.service import resolve_document_file

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


@router.get("/search", response_model=DocumentSearchPageRead)
async def search_documents(
    user: OptionalUser,
    q: str = Query(default="", max_length=500),
    status: Annotated[DocumentStatus | None, Query()] = None,
    policy_area: str | None = Query(default=None, max_length=200),
    country_region: str | None = Query(default=None, max_length=200),
    source_type: str | None = Query(default=None, max_length=200),
    sort: Annotated[DocumentSort, Query()] = "uploaded_desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocumentSearchPageRead:
    return await document_catalogue_repository.search_documents(
        q,
        status=status.value if status else None,
        policy_area=policy_area,
        country_region=country_region,
        source_type=source_type,
        sort=sort,
        page=page,
        page_size=page_size,
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
                resolve_document_file,
                str(document_id),
                include_restricted,
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document file not found") from exc
    return FileResponse(
        path,
        media_type=document_file_store.mime_type_for(document["original_filename"]),
        filename=document["original_filename"],
    )
