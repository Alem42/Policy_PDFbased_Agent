import json
from pathlib import Path
from threading import RLock
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import database
from app.modules.crawling.models import CrawledDocumentModel
from app.modules.crawling.schemas.document import (
    CrawledDocumentAssetRead,
    CrawledDocumentDetailRead,
    CrawledDocumentMetadataRead,
    CrawledDocumentRead,
    CrawledDocumentSearchResultRead,
    CrawledDocumentSnippetRead,
    CrawledDocumentSourceInfoRead,
    CrawledDocumentVersionRead,
)


def crawled_document_model_to_schema(model: CrawledDocumentModel) -> CrawledDocumentRead:
    return CrawledDocumentRead(
        id=model.id,
        crawl_source_id=model.crawl_source_id,
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


def _matches_query(value: object, query: str) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(_matches_query(item, query) for item in value)
    if isinstance(value, dict):
        return any(
            _matches_query(key, query) or _matches_query(item, query) for key, item in value.items()
        )
    return query in str(value).lower()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


class CrawledDocumentRepository:
    """Repository for crawler-discovered documents and their crawl history."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_settings().crawled_document_store_path
        self._crawled_documents: dict[UUID, CrawledDocumentRead] = {}
        self._versions: dict[UUID, list[CrawledDocumentVersionRead]] = {}
        self._assets: dict[UUID, list[CrawledDocumentAssetRead]] = {}
        self._lock = RLock()
        self._load()

    @property
    def uses_database(self) -> bool:
        settings = get_settings()
        return settings.database_enabled and settings.persistence_backend == "database"

    async def list_crawled_documents(
        self,
        crawl_source_id: UUID | None = None,
    ) -> list[CrawledDocumentRead]:
        if not self.uses_database:
            with self._lock:
                crawled_documents = list(self._crawled_documents.values())
                if crawl_source_id is not None:
                    crawled_documents = [
                        item
                        for item in crawled_documents
                        if item.crawl_source_id == crawl_source_id
                    ]
                return sorted(
                    crawled_documents,
                    key=lambda item: item.last_seen_at,
                    reverse=True,
                )

        factory = self.session_factory()
        async with factory() as session:
            statement = select(CrawledDocumentModel).order_by(
                CrawledDocumentModel.last_seen_at.desc()
            )
            if crawl_source_id is not None:
                statement = statement.where(CrawledDocumentModel.crawl_source_id == crawl_source_id)
            models = (await session.scalars(statement)).all()
            return [crawled_document_model_to_schema(model) for model in models]

    async def search_crawled_documents(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[CrawledDocumentSearchResultRead]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        if not self.uses_database:
            return self._search_local_crawled_documents(normalized_query, limit=limit)

        factory = self.session_factory()
        async with factory() as session:
            pattern = f"%{normalized_query}%"
            rows = (
                (
                    await session.execute(
                        text(
                            """
                        select
                          id,
                          canonical_url,
                          title,
                          summary,
                          country,
                          start_year,
                          status,
                          first_seen_at,
                          last_seen_at,
                          metadata,
                          array_remove(array[
                            case when lower(canonical_url) like :pattern
                              then 'canonical_url' end,
                            case when lower(coalesce(title, '')) like :pattern
                              then 'title' end,
                            case when lower(coalesce(summary, '')) like :pattern
                              then 'summary' end,
                            case when lower(coalesce(country, '')) like :pattern
                              then 'country' end,
                            case when lower(metadata::text) like :pattern
                              then 'metadata' end
                          ], null) as match_fields
                        from public.crawled_documents
                        where
                          lower(canonical_url) like :pattern
                          or lower(coalesce(title, '')) like :pattern
                          or lower(coalesce(summary, '')) like :pattern
                          or lower(coalesce(country, '')) like :pattern
                          or lower(metadata::text) like :pattern
                        order by last_seen_at desc
                        limit :limit
                        """
                        ),
                        {"pattern": pattern, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return [
            self._search_result_from_row(
                row,
                match_fields=list(row["match_fields"] or []),
            )
            for row in rows
        ]

    async def get(self, crawled_document_id: UUID) -> CrawledDocumentRead | None:
        if not self.uses_database:
            with self._lock:
                return self._crawled_documents.get(crawled_document_id)
        factory = self.session_factory()
        async with factory() as session:
            model = await session.get(CrawledDocumentModel, crawled_document_id)
            return crawled_document_model_to_schema(model) if model else None

    async def get_detail(
        self,
        crawled_document_id: UUID,
        *,
        snippet_limit: int = 8,
    ) -> CrawledDocumentDetailRead | None:
        document = await self.get(crawled_document_id)
        if document is None:
            return None
        return await self._crawled_detail(document, snippet_limit=snippet_limit)

    async def versions(
        self,
        crawled_document_id: UUID,
    ) -> list[CrawledDocumentVersionRead]:
        if not self.uses_database:
            with self._lock:
                return list(self._versions.get(crawled_document_id, []))
        factory = self.session_factory()
        async with factory() as session:
            statement = (
                select(CrawledDocumentModel)
                .options(selectinload(CrawledDocumentModel.versions))
                .where(CrawledDocumentModel.id == crawled_document_id)
            )
            model = await session.scalar(statement)
            if model is None:
                return []
            return [
                CrawledDocumentVersionRead(
                    id=version.id,
                    crawled_document_id=version.document_id,
                    version=version.version,
                    content_hash=version.content_hash,
                    title=version.title,
                    clean_markdown=version.clean_markdown,
                    metadata=version.metadata_,
                    fetched_at=version.fetched_at,
                )
                for version in sorted(model.versions, key=lambda item: item.version)
            ]

    async def assets(
        self,
        crawled_document_id: UUID,
    ) -> list[CrawledDocumentAssetRead]:
        if not self.uses_database:
            with self._lock:
                return list(self._assets.get(crawled_document_id, []))
        factory = self.session_factory()
        async with factory() as session:
            statement = (
                select(CrawledDocumentModel)
                .options(selectinload(CrawledDocumentModel.assets))
                .where(CrawledDocumentModel.id == crawled_document_id)
            )
            model = await session.scalar(statement)
            if model is None:
                return []
            return [
                CrawledDocumentAssetRead(
                    id=asset.id,
                    crawled_document_id=asset.document_id,
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

    async def _crawled_detail(
        self,
        crawled_document: CrawledDocumentRead,
        *,
        snippet_limit: int,
    ) -> CrawledDocumentDetailRead:
        versions = await self.versions(crawled_document.id)
        assets = await self.assets(crawled_document.id)
        latest_version = max(versions, key=lambda item: item.version, default=None)
        snippets: list[CrawledDocumentSnippetRead] = []
        if latest_version is not None:
            paragraphs = [
                paragraph.strip()
                for paragraph in latest_version.clean_markdown.split("\n\n")
                if paragraph.strip()
            ]
            snippets = [
                CrawledDocumentSnippetRead(
                    version_id=latest_version.id,
                    chunk_index=index,
                    text_preview=_preview(paragraph),
                    metadata=latest_version.metadata,
                )
                for index, paragraph in enumerate(paragraphs[:snippet_limit])
            ]
        source_url = assets[0].original_url if assets else crawled_document.canonical_url
        return CrawledDocumentDetailRead(
            id=crawled_document.id,
            status=crawled_document.status.value,
            first_seen_at=crawled_document.first_seen_at,
            last_seen_at=crawled_document.last_seen_at,
            summary=crawled_document.summary,
            metadata=CrawledDocumentMetadataRead(
                title=crawled_document.title,
                summary=crawled_document.summary,
                country=crawled_document.country,
                policy_status=crawled_document.policy_status,
                start_year=crawled_document.start_year,
                end_year=crawled_document.end_year,
                metadata=crawled_document.metadata,
            ),
            source=CrawledDocumentSourceInfoRead(source_url=source_url),
            snippets=snippets,
            snippet_count=len(snippets),
        )

    @staticmethod
    def _search_result_from_row(
        row,
        *,
        match_fields: list[str],
    ) -> CrawledDocumentSearchResultRead:
        metadata = row["metadata"] or {}
        return CrawledDocumentSearchResultRead(
            id=row["id"],
            canonical_url=row["canonical_url"],
            title=row["title"],
            summary=row["summary"],
            country=row["country"],
            start_year=row["start_year"],
            keywords=_string_list(metadata.get("keywords")),
            status=row["status"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            match_fields=match_fields,
        )

    def _search_local_crawled_documents(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[CrawledDocumentSearchResultRead]:
        with self._lock:
            crawled_documents = sorted(
                self._crawled_documents.values(),
                key=lambda item: item.last_seen_at,
                reverse=True,
            )
        results: list[CrawledDocumentSearchResultRead] = []
        for crawled_document in crawled_documents:
            match_fields = []
            if _matches_query(crawled_document.canonical_url, query):
                match_fields.append("canonical_url")
            if _matches_query(crawled_document.title, query):
                match_fields.append("title")
            if _matches_query(crawled_document.summary, query):
                match_fields.append("summary")
            if _matches_query(crawled_document.country, query):
                match_fields.append("country")
            if _matches_query(crawled_document.metadata, query):
                match_fields.append("metadata")
            if not match_fields:
                continue
            results.append(
                CrawledDocumentSearchResultRead(
                    id=crawled_document.id,
                    canonical_url=crawled_document.canonical_url,
                    title=crawled_document.title,
                    summary=crawled_document.summary,
                    country=crawled_document.country,
                    start_year=crawled_document.start_year,
                    keywords=_string_list(crawled_document.metadata.get("keywords")),
                    status=crawled_document.status.value,
                    first_seen_at=crawled_document.first_seen_at,
                    last_seen_at=crawled_document.last_seen_at,
                    match_fields=match_fields,
                )
            )
            if len(results) >= limit:
                break
        return results

    def save_local(
        self,
        crawled_document: CrawledDocumentRead,
        version: CrawledDocumentVersionRead | None = None,
        assets: list[CrawledDocumentAssetRead] | None = None,
        *,
        persist: bool = True,
    ) -> None:
        with self._lock:
            self._crawled_documents[crawled_document.id] = crawled_document
            if version is not None:
                self._versions.setdefault(crawled_document.id, []).append(version)
            if assets:
                existing = {
                    asset.original_url: asset for asset in self._assets.get(crawled_document.id, [])
                }
                existing.update({asset.original_url: asset for asset in assets})
                self._assets[crawled_document.id] = list(existing.values())
            if persist:
                self._persist()

    def flush_local(self) -> None:
        with self._lock:
            self._persist()

    def _load(self) -> None:
        if not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        raw_documents = payload.get("crawled_documents", payload.get("documents", []))
        for raw in raw_documents:
            item = CrawledDocumentRead.model_validate(raw)
            self._crawled_documents[item.id] = item
        self._versions = {
            UUID(crawled_document_id): [
                CrawledDocumentVersionRead.model_validate(
                    {
                        **raw,
                        "crawled_document_id": raw.get(
                            "crawled_document_id",
                            raw.get("document_id"),
                        ),
                        "clean_markdown": raw.get(
                            "clean_markdown",
                            raw.get("markdown", ""),
                        ),
                    }
                )
                for raw in versions
            ]
            for crawled_document_id, versions in payload.get("versions", {}).items()
        }
        self._assets = {
            UUID(crawled_document_id): [
                CrawledDocumentAssetRead.model_validate(
                    {
                        **raw,
                        "crawled_document_id": raw.get(
                            "crawled_document_id",
                            raw.get("document_id"),
                        ),
                    }
                )
                for raw in assets
            ]
            for crawled_document_id, assets in payload.get("assets", {}).items()
        }

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        payload = {
            "crawled_documents": [
                document.model_dump(mode="json") for document in self._crawled_documents.values()
            ],
            "versions": {
                str(crawled_document_id): [version.model_dump(mode="json") for version in versions]
                for crawled_document_id, versions in self._versions.items()
            },
            "assets": {
                str(crawled_document_id): [asset.model_dump(mode="json") for asset in assets]
                for crawled_document_id, assets in self._assets.items()
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


crawled_document_repository = CrawledDocumentRepository()
