import json
from pathlib import Path
from threading import RLock
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import database
from app.models import CrawledDocumentModel
from app.schemas.document import (
    DocumentAssetRead,
    DocumentDetailRead,
    DocumentMetadataRead,
    DocumentRead,
    DocumentSnippetRead,
    DocumentSourceInfoRead,
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


def _preview(text_value: str, max_length: int = 500) -> str:
    normalized = " ".join(text_value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


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

    async def get_detail(
        self,
        document_id: UUID,
        *,
        snippet_limit: int = 8,
    ) -> DocumentDetailRead | None:
        if not self.uses_database:
            return await self._get_local_detail(document_id, snippet_limit=snippet_limit)

        factory = self.session_factory()
        async with factory() as session:
            processed = (
                await session.execute(
                    text(
                        """
                        select
                          d.id,
                          d.original_filename,
                          d.file_size,
                          d.mime_type,
                          d.status,
                          d.approved,
                          d.access_level,
                          d.uploaded_at,
                          d.processed_at,
                          m.title,
                          m.summary,
                          m.source_type,
                          m.source_organisation,
                          m.country_region,
                          m.language,
                          m.year,
                          m.publication_date,
                          m.policy_areas,
                          m.keywords,
                          m.stakeholders,
                          m.implementation_risks,
                          m.metadata_json
                        from public.documents d
                        left join public.document_metadata m on m.document_id = d.id
                        where d.id = :document_id
                        """
                    ),
                    {"document_id": document_id},
                )
            ).mappings().first()
            if processed is not None:
                snippet_rows = (
                    await session.execute(
                        text(
                            """
                            select
                              id,
                              chunk_index,
                              page_start,
                              page_end,
                              section_title,
                              language,
                              text,
                              token_count,
                              keywords,
                              metadata_json
                            from public.document_chunks
                            where document_id = :document_id
                            order by chunk_index
                            limit :snippet_limit
                            """
                        ),
                        {"document_id": document_id, "snippet_limit": snippet_limit},
                    )
                ).mappings().all()
                snippet_count = (
                    await session.execute(
                        text(
                            """
                            select count(*)
                            from public.document_chunks
                            where document_id = :document_id
                            """
                        ),
                        {"document_id": document_id},
                    )
                ).scalar_one()
                return self._processed_detail_from_rows(
                    processed,
                    snippet_rows,
                    snippet_count,
                )

        document = await self.get(document_id)
        if document is None:
            return None
        return await self._crawled_detail(document, snippet_limit=snippet_limit)

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

    async def _get_local_detail(
        self,
        document_id: UUID,
        *,
        snippet_limit: int,
    ) -> DocumentDetailRead | None:
        with self._lock:
            document = self._documents.get(document_id)
        if document is None:
            return None
        return await self._crawled_detail(document, snippet_limit=snippet_limit)

    async def _crawled_detail(
        self,
        document: DocumentRead,
        *,
        snippet_limit: int,
    ) -> DocumentDetailRead:
        versions = await self.versions(document.id)
        assets = await self.assets(document.id)
        latest_version = max(versions, key=lambda item: item.version, default=None)
        snippets: list[DocumentSnippetRead] = []
        if latest_version is not None:
            paragraphs = [
                paragraph.strip()
                for paragraph in latest_version.clean_markdown.split("\n\n")
                if paragraph.strip()
            ]
            snippets = [
                DocumentSnippetRead(
                    chunk_id=latest_version.id,
                    chunk_index=index,
                    text_preview=_preview(paragraph),
                    metadata=latest_version.metadata,
                )
                for index, paragraph in enumerate(paragraphs[:snippet_limit])
            ]
        source_url = assets[0].original_url if assets else document.canonical_url
        return DocumentDetailRead(
            document_id=document.id,
            status=document.status.value,
            approved=None,
            uploaded_at=document.first_seen_at,
            processed_at=document.last_seen_at,
            summary=document.summary,
            metadata=DocumentMetadataRead(
                title=document.title,
                summary=document.summary,
                country_region=document.country,
                year=document.start_year,
                metadata=document.metadata,
            ),
            source=DocumentSourceInfoRead(
                source_type="crawled_document",
                source_url=source_url,
            ),
            snippets=snippets,
            snippet_count=len(snippets),
        )

    @staticmethod
    def _processed_detail_from_rows(
        document_row,
        snippet_rows,
        snippet_count: int,
    ) -> DocumentDetailRead:
        metadata_json = document_row["metadata_json"] or {}
        source_url = metadata_json.get("source_url") or metadata_json.get("url")
        metadata = DocumentMetadataRead(
            title=document_row["title"],
            summary=document_row["summary"],
            source_type=document_row["source_type"],
            source_organisation=document_row["source_organisation"],
            country_region=document_row["country_region"],
            language=document_row["language"],
            year=document_row["year"],
            publication_date=document_row["publication_date"],
            policy_areas=list(document_row["policy_areas"] or []),
            keywords=list(document_row["keywords"] or []),
            stakeholders=list(document_row["stakeholders"] or []),
            implementation_risks=list(document_row["implementation_risks"] or []),
            metadata=metadata_json,
        )
        return DocumentDetailRead(
            document_id=document_row["id"],
            status=document_row["status"],
            approved=document_row["approved"],
            uploaded_at=document_row["uploaded_at"],
            processed_at=document_row["processed_at"],
            summary=document_row["summary"],
            metadata=metadata,
            source=DocumentSourceInfoRead(
                source_type=document_row["source_type"],
                source_organisation=document_row["source_organisation"],
                source_url=source_url,
                original_filename=document_row["original_filename"],
                mime_type=document_row["mime_type"],
                file_size=document_row["file_size"],
                access_level=document_row["access_level"],
            ),
            snippets=[
                DocumentSnippetRead(
                    chunk_id=row["id"],
                    chunk_index=row["chunk_index"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    section_title=row["section_title"],
                    language=row["language"],
                    text_preview=_preview(row["text"]),
                    token_count=row["token_count"],
                    keywords=list(row["keywords"] or []),
                    metadata=row["metadata_json"] or {},
                )
                for row in snippet_rows
            ],
            snippet_count=snippet_count,
        )

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
