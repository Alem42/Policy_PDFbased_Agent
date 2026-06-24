from uuid import UUID

from pydantic import BaseModel, Field


class ChatFilters(BaseModel):
    policy_area: str | None = None
    country_or_region: str | None = None
    source_organisation: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_year_from: int | None = None
    published_year_to: int | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    document_ids: list[UUID] = Field(default_factory=list)
    filters: ChatFilters = Field(default_factory=ChatFilters)
    top_k: int = Field(default=6, ge=1, le=20)


class Citation(BaseModel):
    document_id: UUID
    title: str
    chunk_id: UUID | None = None
    source_url: str | None = None
    page: int | None = None
    quote: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class DocumentChunkRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    text_preview: str
