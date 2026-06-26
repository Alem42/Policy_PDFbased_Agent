from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.repositories.crawled_document_repository import crawled_document_repository
from app.schemas.crawled_document import (
    CrawledDocumentAssetRead,
    CrawledDocumentDetailRead,
    CrawledDocumentRead,
    CrawledDocumentSearchResultRead,
    CrawledDocumentVersionRead,
)

router = APIRouter(prefix="/crawled-documents", tags=["crawled documents"])


@router.get("", response_model=list[CrawledDocumentRead])
async def list_crawled_documents(
    crawl_source_id: UUID | None = None,
) -> list[CrawledDocumentRead]:
    return await crawled_document_repository.list_crawled_documents(crawl_source_id=crawl_source_id)


@router.get("/search", response_model=list[CrawledDocumentSearchResultRead])
async def search_crawled_documents(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CrawledDocumentSearchResultRead]:
    return await crawled_document_repository.search_crawled_documents(q, limit=limit)


@router.get("/{crawled_document_id}", response_model=CrawledDocumentDetailRead)
async def get_crawled_document(
    crawled_document_id: UUID,
    snippet_limit: int = Query(default=8, ge=0, le=50),
) -> CrawledDocumentDetailRead:
    document = await crawled_document_repository.get_detail(
        crawled_document_id,
        snippet_limit=snippet_limit,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Crawled document not found")
    return document


@router.get(
    "/{crawled_document_id}/versions",
    response_model=list[CrawledDocumentVersionRead],
)
async def list_crawled_document_versions(
    crawled_document_id: UUID,
) -> list[CrawledDocumentVersionRead]:
    if await crawled_document_repository.get(crawled_document_id) is None:
        raise HTTPException(status_code=404, detail="Crawled document not found")
    return await crawled_document_repository.versions(crawled_document_id)


@router.get(
    "/{crawled_document_id}/assets",
    response_model=list[CrawledDocumentAssetRead],
)
async def list_crawled_document_assets(
    crawled_document_id: UUID,
) -> list[CrawledDocumentAssetRead]:
    if await crawled_document_repository.get(crawled_document_id) is None:
        raise HTTPException(status_code=404, detail="Crawled document not found")
    return await crawled_document_repository.assets(crawled_document_id)
