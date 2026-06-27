from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from app.repositories.source_repository import source_repository

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceRead])
async def list_sources() -> list[SourceRead]:
    return await source_repository.list()


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(payload: SourceCreate) -> SourceRead:
    return await source_repository.create(payload)


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(source_id: UUID) -> SourceRead:
    source = await source_repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(source_id: UUID, payload: SourceUpdate) -> SourceRead:
    source = await source_repository.update(source_id, payload)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: UUID) -> None:
    if not await source_repository.delete(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
