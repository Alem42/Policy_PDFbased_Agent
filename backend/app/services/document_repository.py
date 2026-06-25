import json
from pathlib import Path
from threading import RLock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import database
from app.models import CrawledDocumentModel
from app.schemas.document import (
    DocumentAssetRead,
    DocumentRead,
    DocumentVersionRead,
)


def document_model_to_schema(model: CrawledDocumentModel) -> DocumentRead:
    return DocumentRead(
        id=model.id,
        source_id=model.source_id,
        canonical_url=model.canonical_url,
        title=model.title,
        summary=model.summary,
        country=model.country,
        policy_status=model.policy_status,
        start_year=model.start_year,
        end_year=model.end_year,
        content_hash=model.content_hash,
        current_version=model.current_version,
        status=model.status,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        missing_since=model.missing_since,
        metadata=model.metadata_,
    )


class DocumentRepository:
    """Read repository for PostgreSQL, with a durable JSON development fallback."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_settings().document_store_path
        self._documents: dict[UUID, DocumentRead] = {}
        self._versions: dict[UUID, list[DocumentVersionRead]] = {}
        self._assets: dict[UUID, list[DocumentAssetRead]] = {}
        self._lock = RLock()
        self._load()

    @property
    def uses_database(self) -> bool:
        settings = get_settings()
        return settings.database_enabled and settings.persistence_backend == "database"

    async def list_documents(self, source_id: UUID | None = None) -> list[DocumentRead]:
        if not self.uses_database:
            with self._lock:
                documents = list(self._documents.values())
                if source_id is not None:
                    documents = [item for item in documents if item.source_id == source_id]
                return sorted(
                    documents,
                    key=lambda item: item.last_seen_at,
                    reverse=True,
                )

        factory = self.session_factory()
        async with factory() as session:
            statement = select(CrawledDocumentModel).order_by(
                CrawledDocumentModel.last_seen_at.desc()
            )
            if source_id is not None:
                statement = statement.where(CrawledDocumentModel.source_id == source_id)
            models = (await session.scalars(statement)).all()
            return [document_model_to_schema(model) for model in models]

    async def get(self, document_id: UUID) -> DocumentRead | None:
        if not self.uses_database:
            with self._lock:
                return self._documents.get(document_id)
        factory = self.session_factory()
        async with factory() as session:
            model = await session.get(CrawledDocumentModel, document_id)
            return document_model_to_schema(model) if model else None

    async def versions(self, document_id: UUID) -> list[DocumentVersionRead]:
        if not self.uses_database:
            with self._lock:
                return list(self._versions.get(document_id, []))
        factory = self.session_factory()
        async with factory() as session:
            statement = (
                select(CrawledDocumentModel)
                .options(selectinload(CrawledDocumentModel.versions))
                .where(CrawledDocumentModel.id == document_id)
            )
            model = await session.scalar(statement)
            if model is None:
                return []
            return [
                DocumentVersionRead(
                    id=version.id,
                    document_id=version.document_id,
                    version=version.version,
                    content_hash=version.content_hash,
                    title=version.title,
                    clean_markdown=version.clean_markdown,
                    metadata=version.metadata_,
                    fetched_at=version.fetched_at,
                )
                for version in sorted(model.versions, key=lambda item: item.version)
            ]

    async def assets(self, document_id: UUID) -> list[DocumentAssetRead]:
        if not self.uses_database:
            with self._lock:
                return list(self._assets.get(document_id, []))
        factory = self.session_factory()
        async with factory() as session:
            statement = (
                select(CrawledDocumentModel)
                .options(selectinload(CrawledDocumentModel.assets))
                .where(CrawledDocumentModel.id == document_id)
            )
            model = await session.scalar(statement)
            if model is None:
                return []
            return [
                DocumentAssetRead(
                    id=asset.id,
                    document_id=asset.document_id,
                    asset_type=asset.asset_type,
                    original_url=asset.original_url,
                    title=asset.title,
                    mime_type=asset.mime_type,
                    is_available=asset.is_available,
                    http_status=asset.http_status,
                    discovered_at=asset.discovered_at,
                    last_checked_at=asset.last_checked_at,
                    metadata=asset.metadata_,
                )
                for asset in model.assets
            ]

    def save_local(
        self,
        document: DocumentRead,
        version: DocumentVersionRead | None = None,
        assets: list[DocumentAssetRead] | None = None,
        *,
        persist: bool = True,
    ) -> None:
        with self._lock:
            self._documents[document.id] = document
            if version is not None:
                self._versions.setdefault(document.id, []).append(version)
            if assets:
                existing = {
                    asset.original_url: asset for asset in self._assets.get(document.id, [])
                }
                existing.update({asset.original_url: asset for asset in assets})
                self._assets[document.id] = list(existing.values())
            if persist:
                self._persist()

    def flush_local(self) -> None:
        with self._lock:
            self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for raw in payload.get("documents", []):
            item = DocumentRead.model_validate(raw)
            self._documents[item.id] = item
        self._versions = {
            UUID(document_id): [
                DocumentVersionRead.model_validate(
                    {
                        **raw,
                        "clean_markdown": raw.get(
                            "clean_markdown",
                            raw.get("markdown", ""),
                        ),
                    }
                )
                for raw in versions
            ]
            for document_id, versions in payload.get("versions", {}).items()
        }
        self._assets = {
            UUID(document_id): [DocumentAssetRead.model_validate(raw) for raw in assets]
            for document_id, assets in payload.get("assets", {}).items()
        }

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        payload = {
            "documents": [
                document.model_dump(mode="json") for document in self._documents.values()
            ],
            "versions": {
                str(document_id): [version.model_dump(mode="json") for version in versions]
                for document_id, versions in self._versions.items()
            },
            "assets": {
                str(document_id): [asset.model_dump(mode="json") for asset in assets]
                for document_id, assets in self._assets.items()
            },
        }
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self._path)

    @staticmethod
    def session_factory():
        if database.session_factory is None:
            raise RuntimeError("Database session factory is not initialized")
        return database.session_factory


document_repository = DocumentRepository()
