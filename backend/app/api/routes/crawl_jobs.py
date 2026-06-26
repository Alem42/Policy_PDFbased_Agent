from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.repositories.crawl_job_repository import crawl_job_repository
from app.repositories.source_repository import source_repository
from app.schemas.crawl_job import CrawlJobCreate, CrawlJobRead
from app.services.crawl_service import crawl_service

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
    source = await source_repository.get(payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.enabled:
        raise HTTPException(status_code=409, detail="Source is disabled")

    crawl_job = await crawl_job_repository.create(payload)
    background_tasks.add_task(crawl_service.run, crawl_job.id)
    return crawl_job
