from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class CrawlerPreference(StrEnum):
    AUTO = "auto"
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    FIRECRAWL = "firecrawl"


class CrawlSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_url: HttpUrl
    allowed_domains: list[str] = Field(default_factory=list)
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    crawler_preference: CrawlerPreference = CrawlerPreference.AUTO
    max_pages: int | None = Field(default=None, gt=0, le=10000)
    max_documents: int | None = Field(default=None, gt=0, le=10000)
    max_depth: int = Field(default=3, ge=0, le=20)
    enabled: bool = True
    schedule: str | None = Field(
        default=None,
        description="Reserved cron expression for a future scheduler.",
    )
    config: dict[str, Any] = Field(default_factory=dict)


class CrawlSourceCreate(CrawlSourceBase):
    pass


class CrawlSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_url: HttpUrl | None = None
    allowed_domains: list[str] | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    crawler_preference: CrawlerPreference | None = None
    max_pages: int | None = Field(default=None, gt=0, le=10000)
    max_documents: int | None = Field(default=None, gt=0, le=10000)
    max_depth: int | None = Field(default=None, ge=0, le=20)
    enabled: bool | None = None
    schedule: str | None = None
    config: dict[str, Any] | None = None


class CrawlSourceRead(CrawlSourceBase):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
