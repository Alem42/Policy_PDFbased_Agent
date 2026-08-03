from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class CredibilityLevel(StrEnum):
    OFFICIAL = "official"
    ACADEMIC = "academic"
    INSTITUTIONAL = "institutional"
    UNKNOWN = "unknown"


class ProcessingStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    OCR = "ocr"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


class WebLifecycleStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


class AdminDocumentCreateResponse(BaseModel):
    id: UUID
    processing_status: ProcessingStatus = ProcessingStatus.QUEUED


class AdminWebImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=200)


class AdminWebImportResponse(BaseModel):
    id: UUID
    title: str
    source_url: str
    was_duplicate: bool = False
    processing_status: ProcessingStatus = ProcessingStatus.INDEXED


class WebGovernanceRead(BaseModel):
    document_id: UUID
    lifecycle_status: WebLifecycleStatus
    refresh_interval_days: int
    first_imported_at: datetime
    last_fetched_at: datetime
    last_checked_at: datetime | None = None
    next_review_at: datetime
    last_http_status: int | None = None
    last_refresh_error: str | None = None
    content_version: int
    title: str | None = None
    canonical_url: str | None = None
    source_url: str | None = None
    document_status: str | None = None


class WebGovernanceUpdate(BaseModel):
    lifecycle_status: WebLifecycleStatus | None = None
    refresh_interval_days: int | None = Field(default=None, ge=1, le=3650)
    next_review_at: datetime | None = None


class AdminDocumentMetadataUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    source_type: str | None = None
    source_organisation: str | None = None
    country_region: str | None = None
    language: str | None = None
    publication_date: date | None = None
    year: int | None = None
    policy_areas: list[str] | None = None
    keywords: list[str] | None = None
    approved: bool | None = None
    access_level: str | None = None


class DocumentProcessingStatus(BaseModel):
    id: UUID
    status: ProcessingStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
