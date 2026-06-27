from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import database
from app.models import SourceModel
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate


def source_model_to_schema(model: SourceModel) -> SourceRead:
    return SourceRead.model_validate(
        {
            "id": model.id,
            "name": model.name,
            "start_url": model.start_url,
            "allowed_domains": model.allowed_domains,
            "include_patterns": model.include_patterns,
            "exclude_patterns": model.exclude_patterns,
            "crawler_preference": model.crawler_preference,
            "max_pages": model.max_pages,
            "max_documents": model.max_documents,
            "max_depth": model.max_depth,
            "enabled": model.enabled,
            "schedule": model.schedule,
            "config": model.config,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


class SourceRepository:
    def __init__(self) -> None:
        self._memory: dict[UUID, SourceRead] = {}
        self._lock = RLock()

    @property
    def uses_database(self) -> bool:
        settings = get_settings()
        return settings.database_enabled and settings.persistence_backend == "database"

    async def list(self) -> list[SourceRead]:
        if not self.uses_database:
            with self._lock:
                return list(self._memory.values())
        factory = self._session_factory()
        async with factory() as session:
            models = (await session.scalars(select(SourceModel))).all()
            return [source_model_to_schema(model) for model in models]

    async def get(self, source_id: UUID) -> SourceRead | None:
        if not self.uses_database:
            with self._lock:
                return self._memory.get(source_id)
        factory = self._session_factory()
        async with factory() as session:
            model = await session.get(SourceModel, source_id)
            return source_model_to_schema(model) if model else None

    async def create(self, payload: SourceCreate) -> SourceRead:
        if not self.uses_database:
            source = SourceRead(**payload.model_dump())
            with self._lock:
                self._memory[source.id] = source
            return source

        model = SourceModel(
            **payload.model_dump(mode="json"),
        )
        factory = self._session_factory()
        async with factory() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return source_model_to_schema(model)

    async def update(
        self,
        source_id: UUID,
        payload: SourceUpdate,
    ) -> SourceRead | None:
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if not self.uses_database:
            with self._lock:
                current = self._memory.get(source_id)
                if current is None:
                    return None
                updated = current.model_copy(
                    update={**changes, "updated_at": datetime.now(UTC)}
                )
                self._memory[source_id] = updated
                return updated

        factory = self._session_factory()
        async with factory() as session:
            model = await session.get(SourceModel, source_id)
            if model is None:
                return None
            for field, value in changes.items():
                setattr(model, field, value)
            await session.commit()
            await session.refresh(model)
            return source_model_to_schema(model)

    async def delete(self, source_id: UUID) -> bool:
        if not self.uses_database:
            with self._lock:
                return self._memory.pop(source_id, None) is not None
        factory = self._session_factory()
        async with factory() as session:
            result = await session.execute(
                delete(SourceModel).where(SourceModel.id == source_id)
            )
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    def _session_factory():
        if database.session_factory is None:
            raise RuntimeError("Database session factory is not initialized")
        return database.session_factory


source_repository = SourceRepository()
