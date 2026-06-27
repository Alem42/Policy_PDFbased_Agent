from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    ANNOTATED = "annotated"
    READY = "ready"
    FAILED = "failed"


class AccessLevel(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class ProcessingJobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentVersionRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    version: int
    content_hash: str
    title: str | None = None
    clean_markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    access_level: AccessLevel | None = None


class DocumentChunkRead(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    language: str | None = None
    text: str
    token_count: int | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    embedding_model: str | None = None


class DocumentDetailRead(BaseModel):
    id: UUID
    status: DocumentStatus
    approved: bool | None = None
    access_level: AccessLevel | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    summary: str | None = None
    metadata: DocumentMetadataRead
    source: DocumentSourceInfoRead
    page_count: int = 0
    chunk_count: int = 0


class DocumentSearchResultRead(BaseModel):
    id: UUID
    original_filename: str
    title: str | None = None
    summary: str | None = None
    source_organisation: str | None = None
    country_region: str | None = None
    year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    status: DocumentStatus
    approved: bool | None = None
    access_level: AccessLevel | None = None
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    match_fields: list[str] = Field(default_factory=list)
