from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.modules.crawling.repositories.source import crawl_source_repository
from app.modules.crawling.schemas.source import (
    CrawlSourceCreate,
    CrawlSourceRead,
    CrawlSourceUpdate,
)

router = APIRouter(prefix="/crawl-sources", tags=["crawl sources"])


@router.get("", response_model=list[CrawlSourceRead])
async def list_crawl_sources() -> list[CrawlSourceRead]:
    return await crawl_source_repository.list()


@router.post("", response_model=CrawlSourceRead, status_code=status.HTTP_201_CREATED)
async def create_crawl_source(payload: CrawlSourceCreate) -> CrawlSourceRead:
    return await crawl_source_repository.create(payload)


@router.get("/{crawl_source_id}", response_model=CrawlSourceRead)
async def get_crawl_source(crawl_source_id: UUID) -> CrawlSourceRead:
    crawl_source = await crawl_source_repository.get(crawl_source_id)
    if crawl_source is None:
        raise HTTPException(status_code=404, detail="Crawl source not found")
    return crawl_source


@router.patch("/{crawl_source_id}", response_model=CrawlSourceRead)
async def update_crawl_source(
    crawl_source_id: UUID,
    payload: CrawlSourceUpdate,
) -> CrawlSourceRead:
    crawl_source = await crawl_source_repository.update(crawl_source_id, payload)
    if crawl_source is None:
        raise HTTPException(status_code=404, detail="Crawl source not found")
    return crawl_source


@router.delete("/{crawl_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_crawl_source(crawl_source_id: UUID) -> None:
    if not await crawl_source_repository.delete(crawl_source_id):
        raise HTTPException(status_code=404, detail="Crawl source not found")
