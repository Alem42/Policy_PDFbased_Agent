from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import database
from app.models import CrawlJobModel
from app.schemas.job import CrawlJobCreate, CrawlJobRead, CrawlJobStatus


def job_model_to_schema(model: CrawlJobModel) -> CrawlJobRead:
    return CrawlJobRead(
        id=model.id,
        source_id=model.source_id,
        dry_run=model.dry_run,
        status=model.status,
        selected_crawler=model.selected_crawler,
        pages_visited=model.pages_visited,
        expected_documents=model.expected_documents,
        pages_discovered=model.pages_discovered,
        pages_succeeded=model.pages_succeeded,
        pages_failed=model.pages_failed,
        documents_added=model.documents_added,
        documents_updated=model.documents_updated,
        documents_unchanged=model.documents_unchanged,
        documents_missing=model.documents_missing,
        is_complete=model.is_complete,
        message=model.message,
        created_at=model.created_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


class JobRepository:
    def __init__(self) -> None:
        self._memory: dict[UUID, CrawlJobRead] = {}
        self._lock = RLock()

    @property
    def uses_database(self) -> bool:
        settings = get_settings()
        return settings.database_enabled and settings.persistence_backend == "database"

    async def list(self) -> list[CrawlJobRead]:
        if not self.uses_database:
            with self._lock:
                return sorted(
                    self._memory.values(),
                    key=lambda item: item.created_at,
                    reverse=True,
                )
        factory = self._session_factory()
        async with factory() as session:
            statement = select(CrawlJobModel).order_by(CrawlJobModel.created_at.desc())
            models = (await session.scalars(statement)).all()
            return [job_model_to_schema(model) for model in models]

    async def get(self, job_id: UUID) -> CrawlJobRead | None:
        if not self.uses_database:
            with self._lock:
                return self._memory.get(job_id)
        factory = self._session_factory()
        async with factory() as session:
            model = await session.get(CrawlJobModel, job_id)
            return job_model_to_schema(model) if model else None

    async def create(self, payload: CrawlJobCreate) -> CrawlJobRead:
        if not self.uses_database:
            job = CrawlJobRead(**payload.model_dump())
            with self._lock:
                self._memory[job.id] = job
            return job

        model = CrawlJobModel(**payload.model_dump())
        factory = self._session_factory()
        async with factory() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return job_model_to_schema(model)

    async def update(self, job_id: UUID, **changes: Any) -> CrawlJobRead | None:
        if changes.get("finished_at") is True:
            changes["finished_at"] = datetime.now(UTC)
        if not self.uses_database:
            with self._lock:
                job = self._memory.get(job_id)
                if job is None:
                    return None
                updated = job.model_copy(update=changes)
                self._memory[job_id] = updated
                return updated

        factory = self._session_factory()
        async with factory() as session:
            model = await session.get(CrawlJobModel, job_id)
            if model is None:
                return None
            for field, value in changes.items():
                setattr(model, field, value)
            await session.commit()
            await session.refresh(model)
            return job_model_to_schema(model)

    async def fail_interrupted_running_jobs(self) -> int:
        now = datetime.now(UTC)
        message = "Server restarted before this crawl completed; please start a new crawl."
        if not self.uses_database:
            with self._lock:
                count = 0
                for job_id, job in list(self._memory.items()):
                    if job.status != CrawlJobStatus.RUNNING:
                        continue
                    self._memory[job_id] = job.model_copy(
                        update={
                            "status": CrawlJobStatus.FAILED,
                            "message": message,
                            "finished_at": now,
                        }
                    )
                    count += 1
                return count

        factory = self._session_factory()
        async with factory() as session:
            result = await session.execute(
                update(CrawlJobModel)
                .where(CrawlJobModel.status == CrawlJobStatus.RUNNING)
                .values(
                    status=CrawlJobStatus.FAILED,
                    message=message,
                    finished_at=now,
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    @staticmethod
    def _session_factory():
        if database.session_factory is None:
            raise RuntimeError("Database session factory is not initialized")
        return database.session_factory


job_repository = JobRepository()
