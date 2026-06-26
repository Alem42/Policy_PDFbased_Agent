from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CrawlJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CrawlJobCreate(BaseModel):
    source_id: UUID
    dry_run: bool = Field(
        default=True,
        description="Plan the crawl without contacting the target website.",
    )


class CrawlJobRead(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    dry_run: bool = True
    status: CrawlJobStatus = CrawlJobStatus.PENDING
    selected_crawler: str | None = None
    pages_visited: int = 0
    expected_documents: int | None = None
    pages_discovered: int = 0
    pages_succeeded: int = 0
    pages_failed: int = 0
    documents_added: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    documents_missing: int = 0
    is_complete: bool | None = None
    message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
