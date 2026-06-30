from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.modules.crawling.repositories.job import crawl_job_repository
from app.modules.crawling.repositories.source import crawl_source_repository
from app.modules.crawling.schemas.job import CrawlJobCreate, CrawlJobRead
from app.modules.crawling.service import crawl_service

router = APIRouter(prefix="/crawl-jobs", tags=["crawl jobs"])


@router.get("", response_model=list[CrawlJobRead])
async def list_crawl_jobs() -> list[CrawlJobRead]:
    return await crawl_job_repository.list()


@router.get("/{crawl_job_id}", response_model=CrawlJobRead)
async def get_crawl_job(crawl_job_id: UUID) -> CrawlJobRead:
    crawl_job = await crawl_job_repository.get(crawl_job_id)
    if crawl_job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return crawl_job


@router.post("", response_model=CrawlJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_crawl_job(
    payload: CrawlJobCreate,
    background_tasks: BackgroundTasks,
) -> CrawlJobRead:
    crawl_source = await crawl_source_repository.get(payload.crawl_source_id)
    if crawl_source is None:
        raise HTTPException(status_code=404, detail="Crawl source not found")
    if not crawl_source.enabled:
        raise HTTPException(status_code=409, detail="Crawl source is disabled")

    crawl_job = await crawl_job_repository.create(payload)
    background_tasks.add_task(crawl_service.run, crawl_job.id)
    return crawl_job
