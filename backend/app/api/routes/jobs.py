from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.schemas.job import CrawlJobCreate, CrawlJobRead
from app.services.crawl_service import crawl_service
from app.services.job_repository import job_repository
from app.services.source_repository import source_repository

router = APIRouter(prefix="/crawl-jobs", tags=["crawl jobs"])


@router.get("", response_model=list[CrawlJobRead])
async def list_jobs() -> list[CrawlJobRead]:
    return await job_repository.list()


@router.get("/{job_id}", response_model=CrawlJobRead)
async def get_job(job_id: UUID) -> CrawlJobRead:
    job = await job_repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return job


@router.post("", response_model=CrawlJobRead, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: CrawlJobCreate,
    background_tasks: BackgroundTasks,
) -> CrawlJobRead:
    source = await source_repository.get(payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.enabled:
        raise HTTPException(status_code=409, detail="Source is disabled")

    job = await job_repository.create(payload)
    background_tasks.add_task(crawl_service.run, job.id)
    return job
