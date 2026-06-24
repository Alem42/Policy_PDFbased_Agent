from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.schemas.crawler import CrawlJobCreate, CrawlJobRead, TrustedSourceCreate, TrustedSourceRead

router = APIRouter(tags=["crawlers"])


@router.post(
    "/trusted-sources",
    response_model=TrustedSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_trusted_source(payload: TrustedSourceCreate) -> TrustedSourceRead:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Trusted source placeholder. Implement in feature/crawler-sources.",
    )


@router.get("/trusted-sources", response_model=list[TrustedSourceRead])
async def list_trusted_sources() -> list[TrustedSourceRead]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Trusted source listing placeholder. Implement in feature/crawler-sources.",
    )


@router.post("/crawl-jobs", response_model=CrawlJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_crawl_job(payload: CrawlJobCreate) -> CrawlJobRead:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Crawl job placeholder. Implement in feature/crawler-sources.",
    )


@router.get("/crawl-jobs/{job_id}", response_model=CrawlJobRead)
async def get_crawl_job(job_id: UUID) -> CrawlJobRead:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Crawl job status placeholder. Implement in feature/crawler-sources.",
    )
