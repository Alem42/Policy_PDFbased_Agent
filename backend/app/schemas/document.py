from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class DocumentRead(BaseModel):
    id: UUID
    title: str
    name: str | None = None
    original_filename: str | None = None
    stored_filename: str | None = None
    relative_path: str | None = None
    size: int | None = None
    modified_at: float | None = None
    summary: str | None = None
    source_type: str | None = None
    source_organisation: str | None = None
    source_url: str | None = None
    policy_area: str | None = None
    policy_areas: list[str] = Field(default_factory=list)
    country_or_region: str | None = None
    country_region: str | None = None
    language: str | None = None
    published_year: int | None = None
    year: int | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    credibility_level: str = "unknown"
    processing_status: str = "queued"
    page_count: int = 0
    chunk_count: int = 0
    approved: bool = True
    access_level: str = "public"
    processed_at: str | None = None
    error_message: str | None = None
    publication_date: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    status: str = DocumentStatus.ACTIVE
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
