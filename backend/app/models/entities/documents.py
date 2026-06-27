from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.schemas.document import AccessLevel, DocumentStatus, ProcessingJobStatus


class Vector384(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        return "vector(384)"


class DocumentModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_approved_access", "approved", "access_level"),
    )

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sql_text("'application/pdf'")
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Text, nullable=False, server_default=sql_text("'uploaded'")
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sql_text("true"))
    access_level: Mapped[AccessLevel] = mapped_column(
        Text, nullable=False, server_default=sql_text("'public'")
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    metadata_record: Mapped["DocumentMetadataModel | None"] = relationship(
        back_populates="document", uselist=False
    )
    chunks: Mapped[list["DocumentChunkModel"]] = relationship(back_populates="document")
    pages: Mapped[list["DocumentPageModel"]] = relationship(back_populates="document")
    processing_jobs: Mapped[list["ProcessingJobModel"]] = relationship(back_populates="document")


class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"
    __table_args__ = (
        Index("idx_document_metadata_keywords", "keywords", postgresql_using="gin"),
        Index("idx_document_metadata_policy_areas", "policy_areas", postgresql_using="gin"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(Text)
    source_organisation: Mapped[str | None] = mapped_column(Text)
    country_region: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    publication_date: Mapped[date | None] = mapped_column(Date)
    policy_areas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    stakeholders: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    implementation_risks: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    generated_by_model: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[DocumentModel] = relationship(back_populates="metadata_record")


class DocumentChunkModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("idx_document_chunks_document_id", "document_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[DocumentModel] = relationship(back_populates="chunks")
    embedding: Mapped["ChunkEmbeddingModel | None"] = relationship(
        back_populates="chunk", uselist=False
    )


class DocumentPageModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        Index("idx_document_pages_document_id", "document_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("''"))
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[DocumentModel] = relationship(back_populates="pages")


class ChunkEmbeddingModel(Base):
    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[Any] = mapped_column(Vector384(), nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunk: Mapped[DocumentChunkModel] = relationship(back_populates="embedding")


class ProcessingJobModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "processing_jobs"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProcessingJobStatus] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )

    document: Mapped[DocumentModel] = relationship(back_populates="processing_jobs")
