import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crawlers.base import CrawledDocument
from app.models import (
    CrawledDocumentAssetModel,
    CrawledDocumentModel,
    CrawledDocumentVersionModel,
)
from app.schemas.document import (
    CrawledDocumentRead,
    DocumentAssetRead,
    DocumentStatus,
    DocumentVersionRead,
    IncrementalSyncStats,
)
from app.repositories.crawled_document_repository import (
    CrawledDocumentRepository,
    crawled_document_repository,
)


class IncrementalSyncService:
    def __init__(self, repository: CrawledDocumentRepository) -> None:
        self.repository = repository

    async def sync(
        self,
        source_id: UUID,
        crawled_documents: list[CrawledDocument],
        *,
        crawl_job_id: UUID | None = None,
        mark_missing: bool = False,
    ) -> IncrementalSyncStats:
        if self.repository.uses_database:
            return await self._sync_database(
                source_id,
                crawled_documents,
                crawl_job_id=crawl_job_id,
                mark_missing=mark_missing,
            )
        return self._sync_local(
            source_id,
            crawled_documents,
            mark_missing=mark_missing,
        )

    async def _sync_database(
        self,
        source_id: UUID,
        crawled_documents: list[CrawledDocument],
        *,
        crawl_job_id: UUID | None,
        mark_missing: bool,
    ) -> IncrementalSyncStats:
        stats = IncrementalSyncStats()
        seen_urls: set[str] = set()
        factory = self.repository.session_factory()

        async with factory() as session:
            statement = (
                select(CrawledDocumentModel)
                .options(selectinload(CrawledDocumentModel.assets))
                .where(CrawledDocumentModel.source_id == source_id)
            )
            existing_models = (await session.scalars(statement)).all()
            existing_by_url = {model.canonical_url: model for model in existing_models}
            asset_urls_by_document = {
                model.id: {asset.original_url for asset in model.assets}
                for model in existing_models
            }

            for crawled in crawled_documents:
                canonical_url = canonicalize_url(crawled.url)
                if canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)
                content_hash = calculate_content_hash(crawled)
                existing = existing_by_url.get(canonical_url)
                now = datetime.now(UTC)
                structured = crawled.metadata.get("structured", {})

                if existing is None:
                    existing = CrawledDocumentModel(
                        source_id=source_id,
                        canonical_url=canonical_url,
                        title=crawled.title,
                        summary=structured.get("summary"),
                        country=structured.get("country"),
                        policy_status=structured.get("policy_status"),
                        start_year=structured.get("start_year"),
                        end_year=structured.get("end_year"),
                        content_hash=content_hash,
                        current_version=1,
                        status=DocumentStatus.ACTIVE,
                        first_seen_at=now,
                        last_seen_at=now,
                        metadata_=crawled.metadata,
                    )
                    session.add(existing)
                    await session.flush()
                    session.add(self._database_version(existing, crawled, crawl_job_id))
                    existing_by_url[canonical_url] = existing
                    asset_urls_by_document[existing.id] = set()
                    stats.added += 1
                elif existing.content_hash == content_hash:
                    existing.last_seen_at = now
                    existing.status = DocumentStatus.ACTIVE
                    existing.missing_since = None
                    stats.unchanged += 1
                else:
                    existing.title = crawled.title
                    existing.summary = structured.get("summary")
                    existing.country = structured.get("country")
                    existing.policy_status = structured.get("policy_status")
                    existing.start_year = structured.get("start_year")
                    existing.end_year = structured.get("end_year")
                    existing.content_hash = content_hash
                    existing.current_version += 1
                    existing.status = DocumentStatus.ACTIVE
                    existing.last_seen_at = now
                    existing.missing_since = None
                    existing.metadata_ = crawled.metadata
                    session.add(self._database_version(existing, crawled, crawl_job_id))
                    stats.updated += 1

                self._merge_database_assets(
                    session,
                    existing,
                    crawled,
                    asset_urls_by_document[existing.id],
                )

            if mark_missing:
                now = datetime.now(UTC)
                for document in existing_models:
                    if (
                        document.canonical_url not in seen_urls
                        and document.status == DocumentStatus.ACTIVE
                    ):
                        document.status = DocumentStatus.MISSING
                        document.missing_since = now
                        stats.missing += 1

            await session.commit()
        return stats

    def _sync_local(
        self,
        source_id: UUID,
        crawled_documents: list[CrawledDocument],
        *,
        mark_missing: bool,
    ) -> IncrementalSyncStats:
        stats = IncrementalSyncStats()
        seen_urls: set[str] = set()
        existing_documents = {
            item.canonical_url: item
            for item in self.repository._documents.values()
            if item.source_id == source_id
        }

        for crawled in crawled_documents:
            canonical_url = canonicalize_url(crawled.url)
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)
            content_hash = calculate_content_hash(crawled)
            existing = existing_documents.get(canonical_url)
            now = datetime.now(UTC)
            structured = crawled.metadata.get("structured", {})

            if existing is None:
                document = CrawledDocumentRead(
                    source_id=source_id,
                    canonical_url=canonical_url,
                    title=crawled.title,
                    summary=structured.get("summary"),
                    country=structured.get("country"),
                    policy_status=structured.get("policy_status"),
                    start_year=structured.get("start_year"),
                    end_year=structured.get("end_year"),
                    content_hash=content_hash,
                    metadata=crawled.metadata,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                version = self._local_version(document, crawled)
                assets = self._local_assets(document.id, crawled)
                self.repository.save_local(
                    document,
                    version,
                    assets,
                    persist=False,
                )
                existing_documents[canonical_url] = document
                stats.added += 1
                continue

            if existing.content_hash == content_hash:
                document = existing.model_copy(
                    update={
                        "last_seen_at": now,
                        "status": DocumentStatus.ACTIVE,
                        "missing_since": None,
                    }
                )
                self.repository.save_local(
                    document,
                    assets=self._local_assets(document.id, crawled),
                    persist=False,
                )
                stats.unchanged += 1
                continue

            document = existing.model_copy(
                update={
                    "title": crawled.title,
                    "summary": structured.get("summary"),
                    "country": structured.get("country"),
                    "policy_status": structured.get("policy_status"),
                    "start_year": structured.get("start_year"),
                    "end_year": structured.get("end_year"),
                    "content_hash": content_hash,
                    "current_version": existing.current_version + 1,
                    "status": DocumentStatus.ACTIVE,
                    "last_seen_at": now,
                    "missing_since": None,
                    "metadata": crawled.metadata,
                }
            )
            self.repository.save_local(
                document,
                self._local_version(document, crawled),
                self._local_assets(document.id, crawled),
                persist=False,
            )
            stats.updated += 1

        if mark_missing:
            for document in list(existing_documents.values()):
                if (
                    document.canonical_url not in seen_urls
                    and document.status == DocumentStatus.ACTIVE
                ):
                    self.repository.save_local(
                        document.model_copy(
                            update={
                                "status": DocumentStatus.MISSING,
                                "missing_since": datetime.now(UTC),
                            }
                        ),
                        persist=False,
                    )
                    stats.missing += 1

        self.repository.flush_local()
        return stats

    @staticmethod
    def _database_version(
        document: CrawledDocumentModel,
        crawled: CrawledDocument,
        crawl_job_id: UUID | None,
    ) -> CrawledDocumentVersionModel:
        return CrawledDocumentVersionModel(
            document_id=document.id,
            crawl_job_id=crawl_job_id,
            version=document.current_version,
            content_hash=document.content_hash,
            title=crawled.title,
            clean_markdown=crawled.markdown or "",
            metadata_=crawled.metadata,
        )

    @staticmethod
    def _merge_database_assets(
        session: AsyncSession,
        document: CrawledDocumentModel,
        crawled: CrawledDocument,
        existing: set[str],
    ) -> None:
        for raw in crawled.metadata.get("assets", []):
            url = raw.get("url")
            if not url or url in existing:
                continue
            session.add(
                CrawledDocumentAssetModel(
                    document_id=document.id,
                    asset_type=raw.get("asset_type", "link"),
                    original_url=url,
                    title=raw.get("title"),
                    mime_type=raw.get("mime_type"),
                    metadata_=raw.get("metadata", {}),
                )
            )
            existing.add(url)

    @staticmethod
    def _local_version(
        document: CrawledDocumentRead,
        crawled: CrawledDocument,
    ) -> DocumentVersionRead:
        return DocumentVersionRead(
            document_id=document.id,
            version=document.current_version,
            content_hash=document.content_hash,
            title=crawled.title,
            clean_markdown=crawled.markdown or "",
            metadata=crawled.metadata,
        )

    @staticmethod
    def _local_assets(
        document_id: UUID,
        crawled: CrawledDocument,
    ) -> list[DocumentAssetRead]:
        return [
            DocumentAssetRead(
                document_id=document_id,
                asset_type=raw.get("asset_type", "link"),
                original_url=raw["url"],
                title=raw.get("title"),
                mime_type=raw.get("mime_type"),
                metadata=raw.get("metadata", {}),
            )
            for raw in crawled.metadata.get("assets", [])
            if raw.get("url")
        ]


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            query,
            "",
        )
    )


def calculate_content_hash(document: CrawledDocument) -> str:
    payload = {
        "title": document.title or "",
        "content": document.markdown or "",
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


incremental_sync_service = IncrementalSyncService(crawled_document_repository)
