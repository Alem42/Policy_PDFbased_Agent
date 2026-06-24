from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class CrawlJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TrustedSourceCreate(BaseModel):
    name: str
    start_url: str
    allowed_domains: list[str] = Field(default_factory=list)
    policy_area: str | None = None
    enabled: bool = True


class TrustedSourceRead(TrustedSourceCreate):
    id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawlJobCreate(BaseModel):
    trusted_source_id: UUID
    dry_run: bool = True
    max_pages: int = Field(default=20, ge=1, le=1000)


class CrawlJobRead(BaseModel):
    id: UUID
    trusted_source_id: UUID
    status: CrawlJobStatus = CrawlJobStatus.QUEUED
    message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
