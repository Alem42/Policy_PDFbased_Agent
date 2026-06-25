from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"


class DocumentVersionRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    version: int
    content_hash: str
    title: str | None = None
    clean_markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    canonical_url: str
    title: str | None = None
    summary: str | None = None
    country: str | None = None
    policy_status: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    content_hash: str
    current_version: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    missing_since: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentAssetRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    asset_type: str = "link"
    original_url: str
    title: str | None = None
    mime_type: str | None = None
    is_available: bool | None = None
    http_status: int | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_checked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentMetadataRead(BaseModel):
    title: str | None = None
    summary: str | None = None
    source_type: str | None = None
    source_organisation: str | None = None
    country_region: str | None = None
    language: str | None = None
    year: int | None = None
    publication_date: date | None = None
    policy_areas: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    implementation_risks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentSourceInfoRead(BaseModel):
    source_type: str | None = None
    source_organisation: str | None = None
    source_url: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    access_level: str | None = None


class DocumentSnippetRead(BaseModel):
    chunk_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    language: str | None = None
    text_preview: str
    token_count: int | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentDetailRead(BaseModel):
    document_id: UUID
    status: str
    approved: bool | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    summary: str | None = None
    metadata: DocumentMetadataRead
    source: DocumentSourceInfoRead
    snippets: list[DocumentSnippetRead] = Field(default_factory=list)
    snippet_count: int = 0


class DocumentSearchResultRead(BaseModel):
    document_id: UUID
    original_filename: str
    title: str | None = None
    summary: str | None = None
    source_organisation: str | None = None
    country_region: str | None = None
    year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    status: str
    approved: bool | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    match_fields: list[str] = Field(default_factory=list)


class IncrementalSyncStats(BaseModel):
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
