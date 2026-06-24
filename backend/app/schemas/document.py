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
    summary: str | None = None
    source_organisation: str | None = None
    source_url: str | None = None
    policy_area: str | None = None
    country_or_region: str | None = None
    published_year: int | None = None
    tags: list[str] = Field(default_factory=list)
    credibility_level: str = "unknown"
    processing_status: str = "queued"
    status: DocumentStatus = DocumentStatus.ACTIVE
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
