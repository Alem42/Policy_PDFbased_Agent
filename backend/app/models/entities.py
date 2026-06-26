from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.schemas.crawled_document import CrawledDocumentStatus
from app.schemas.job import CrawlJobStatus
from app.schemas.source import CrawlerPreference


class SourceModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    allowed_domains: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    include_patterns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    exclude_patterns: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    crawler_preference: Mapped[CrawlerPreference] = mapped_column(
        Enum(
            CrawlerPreference,
            name="crawler_preference",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        default=CrawlerPreference.AUTO,
    )
    max_pages: Mapped[int | None] = mapped_column(Integer)
    max_documents: Mapped[int | None] = mapped_column(Integer)
    max_depth: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    jobs: Mapped[list["CrawlJobModel"]] = relationship(back_populates="source")
    crawled_documents: Mapped[list["CrawledDocumentModel"]] = relationship(
        back_populates="source"
    )


class CrawlJobModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        Index("crawl_jobs_source_created_idx", "source_id", "created_at"),
        Index("crawl_jobs_status_idx", "status"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[CrawlJobStatus] = mapped_column(
        Enum(
            CrawlJobStatus,
            name="crawl_job_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        default=CrawlJobStatus.PENDING,
    )
    selected_crawler: Mapped[str | None] = mapped_column(Text)
    pages_visited: Mapped[int] = mapped_column(Integer, default=0)
    expected_documents: Mapped[int | None] = mapped_column(Integer)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    documents_added: Mapped[int] = mapped_column(Integer, default=0)
    documents_updated: Mapped[int] = mapped_column(Integer, default=0)
    documents_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    documents_missing: Mapped[int] = mapped_column(Integer, default=0)
    is_complete: Mapped[bool | None] = mapped_column(Boolean)
    message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[SourceModel] = relationship(back_populates="jobs")


class CrawledDocumentModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawled_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "canonical_url",
            name="crawled_documents_source_url_unique",
        ),
        Index("crawled_documents_source_status_idx", "source_id", "status"),
        Index("crawled_documents_last_seen_idx", "last_seen_at"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    policy_status: Mapped[str | None] = mapped_column(Text)
    start_year: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[CrawledDocumentStatus] = mapped_column(
        Enum(
            CrawledDocumentStatus,
            name="crawled_document_status",
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=False,
        ),
        default=CrawledDocumentStatus.ACTIVE,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    source: Mapped[SourceModel] = relationship(back_populates="crawled_documents")
    versions: Mapped[list["CrawledDocumentVersionModel"]] = relationship(
        back_populates="crawled_document"
    )
    assets: Mapped[list["CrawledDocumentAssetModel"]] = relationship(
        back_populates="crawled_document"
    )


class CrawledDocumentVersionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawled_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version",
            name="crawled_document_versions_number_unique",
        ),
        Index("crawled_document_versions_document_fetched_idx", "document_id", "fetched_at"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawled_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    crawl_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    clean_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    crawled_document: Mapped[CrawledDocumentModel] = relationship(back_populates="versions")


class CrawledDocumentAssetModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "crawled_document_assets"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "original_url",
            name="crawled_document_assets_document_url_unique",
        ),
        Index("crawled_document_assets_document_idx", "document_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawled_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(Text, default="link")
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    is_available: Mapped[bool | None] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    crawled_document: Mapped[CrawledDocumentModel] = relationship(back_populates="assets")


class DocumentModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "documents"

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool | None] = mapped_column(Boolean)
    access_level: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    metadata_record: Mapped["DocumentMetadataModel | None"] = relationship(
        back_populates="document",
        uselist=False,
    )
    chunks: Mapped[list["DocumentChunkModel"]] = relationship(back_populates="document")


class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(Text)
    source_organisation: Mapped[str | None] = mapped_column(Text)
    country_region: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    publication_date: Mapped[date | None] = mapped_column(Date)
    policy_areas: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    stakeholders: Mapped[str | None] = mapped_column(Text)
    implementation_risks: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    generated_by_model: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[DocumentModel] = relationship(back_populates="metadata_record")


class DocumentChunkModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("document_chunks_document_idx", "document_id", "chunk_index"),)

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    keywords: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    document: Mapped[DocumentModel] = relationship(back_populates="chunks")


class CrawlErrorModel(Base):
    __tablename__ = "crawl_errors"
    __table_args__ = (Index("crawl_errors_job_idx", "crawl_job_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crawl_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(Text)
    crawler: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
