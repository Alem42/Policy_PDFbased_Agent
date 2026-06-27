from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.schemas.crawl_job import CrawlJobStatus
from app.schemas.crawl_source import CrawlerPreference
from app.schemas.crawled_document import CrawledDocumentStatus


class CrawlSourceModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_sources"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    allowed_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    include_patterns: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    exclude_patterns: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    crawler_preference: Mapped[CrawlerPreference] = mapped_column(
        Enum(
            CrawlerPreference,
            name="crawler_preference",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        nullable=False,
        server_default=text("'auto'"),
    )
    max_pages: Mapped[int | None] = mapped_column(Integer)
    max_documents: Mapped[int | None] = mapped_column(Integer)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    schedule: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    crawl_jobs: Mapped[list["CrawlJobModel"]] = relationship(back_populates="crawl_source")
    crawled_documents: Mapped[list["CrawledDocumentModel"]] = relationship(
        back_populates="crawl_source"
    )


class CrawlJobModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        Index("crawl_jobs_crawl_source_created_idx", "crawl_source_id", "created_at"),
        Index("crawl_jobs_status_idx", "status"),
    )

    crawl_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_sources.id", ondelete="CASCADE"), nullable=False
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[CrawlJobStatus] = mapped_column(
        Enum(
            CrawlJobStatus,
            name="crawl_job_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    selected_crawler: Mapped[str | None] = mapped_column(Text)
    pages_visited: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    expected_documents: Mapped[int | None] = mapped_column(Integer)
    pages_discovered: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pages_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    documents_added: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    documents_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    documents_unchanged: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    documents_missing: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_complete: Mapped[bool | None] = mapped_column(Boolean)
    message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    crawl_source: Mapped[CrawlSourceModel] = relationship(back_populates="crawl_jobs")


class CrawledDocumentModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawled_documents"
    __table_args__ = (
        UniqueConstraint(
            "crawl_source_id",
            "canonical_url",
            name="crawled_documents_crawl_source_url_unique",
        ),
        Index("crawled_documents_crawl_source_status_idx", "crawl_source_id", "status"),
        Index("crawled_documents_last_seen_idx", "last_seen_at"),
    )

    crawl_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_sources.id", ondelete="CASCADE"), nullable=False
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    policy_status: Mapped[str | None] = mapped_column(Text)
    start_year: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[CrawledDocumentStatus] = mapped_column(
        Enum(
            CrawledDocumentStatus,
            name="document_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        nullable=False,
        server_default=text("'active'"),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    crawl_source: Mapped[CrawlSourceModel] = relationship(back_populates="crawled_documents")
    versions: Mapped[list["CrawledDocumentVersionModel"]] = relationship(
        back_populates="crawled_document"
    )
    assets: Mapped[list["CrawledDocumentAssetModel"]] = relationship(
        back_populates="crawled_document"
    )


class CrawledDocumentVersionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawled_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="crawled_document_versions_number_unique"),
        Index("crawled_document_versions_document_fetched_idx", "document_id", "fetched_at"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawled_documents.id", ondelete="CASCADE"), nullable=False
    )
    crawl_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    clean_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crawled_document: Mapped[CrawledDocumentModel] = relationship(back_populates="versions")


class CrawledDocumentAssetModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawled_document_assets"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "original_url", name="crawled_document_assets_document_url_unique"
        ),
        Index("crawled_document_assets_document_idx", "document_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawled_documents.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'link'"))
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    is_available: Mapped[bool | None] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    crawled_document: Mapped[CrawledDocumentModel] = relationship(back_populates="assets")


class CrawlErrorModel(Base):
    __tablename__ = "crawl_errors"
    __table_args__ = (Index("crawl_errors_job_idx", "crawl_job_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    crawl_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False
    )
    crawl_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_sources.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str | None] = mapped_column(Text)
    crawler: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
