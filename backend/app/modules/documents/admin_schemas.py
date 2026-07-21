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


class AdminDocumentCreateResponse(BaseModel):
    id: UUID
    processing_status: ProcessingStatus = ProcessingStatus.QUEUED


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
