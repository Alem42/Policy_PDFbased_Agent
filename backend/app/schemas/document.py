from datetime import UTC, datetime
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


class IncrementalSyncStats(BaseModel):
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
