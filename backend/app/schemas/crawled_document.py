from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CrawledDocumentStatus(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"


class CrawledDocumentVersionRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    crawled_document_id: UUID
    version: int
    content_hash: str
    title: str | None = None
    clean_markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawledDocumentRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    crawl_source_id: UUID
    canonical_url: str
    title: str | None = None
    summary: str | None = None
    country: str | None = None
    policy_status: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    content_hash: str
    current_version: int = 1
    status: CrawledDocumentStatus = CrawledDocumentStatus.ACTIVE
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    missing_since: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawledDocumentAssetRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    crawled_document_id: UUID
    asset_type: str = "link"
    original_url: str
    title: str | None = None
    mime_type: str | None = None
    is_available: bool | None = None
    http_status: int | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_checked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawledDocumentMetadataRead(BaseModel):
    title: str | None = None
    summary: str | None = None
    country: str | None = None
    policy_status: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawledDocumentSourceInfoRead(BaseModel):
    source_url: str | None = None
    source_type: str = "crawled_document"


class CrawledDocumentSnippetRead(BaseModel):
    version_id: UUID
    chunk_index: int
    text_preview: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrawledDocumentDetailRead(BaseModel):
    crawled_document_id: UUID
    status: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    summary: str | None = None
    metadata: CrawledDocumentMetadataRead
    source: CrawledDocumentSourceInfoRead
    snippets: list[CrawledDocumentSnippetRead] = Field(default_factory=list)
    snippet_count: int = 0


class CrawledDocumentSearchResultRead(BaseModel):
    crawled_document_id: UUID
    canonical_url: str
    title: str | None = None
    summary: str | None = None
    country: str | None = None
    start_year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    status: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    match_fields: list[str] = Field(default_factory=list)


class IncrementalSyncStats(BaseModel):
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
