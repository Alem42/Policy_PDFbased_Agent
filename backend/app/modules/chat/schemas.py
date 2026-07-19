from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ResponseMode = Literal["researcher", "student"]
AnswerMode = Literal["analysis", "chat"]

# Maximum number of prior conversation turns sent to the LLM for context.
# Each turn = one user message + one assistant reply (2 messages).
# Increase this value if users need longer memory; decrease to save tokens.
MAX_HISTORY_TURNS = 5


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


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
    filenames: list[str] = Field(default_factory=list)
    filters: ChatFilters = Field(default_factory=ChatFilters)
    top_k: int = Field(default=6, ge=1, le=20)
    model: str | None = None
    response_mode: ResponseMode = "researcher"
    answer_mode: AnswerMode = "analysis"
    # When session_id is provided the backend reads history from the DB directly.
    # When None a new session is created automatically.
    session_id: UUID | None = None
    # Kept for backwards-compat with clients that still send history inline.
    # DB history takes precedence when session_id is set.
    history: list[ChatMessage] = Field(default_factory=list)


class Citation(BaseModel):
    document_id: UUID | None = None  # None when built from page-level fallback
    title: str
    chunk_id: UUID | None = None
    source_url: str | None = None
    page: int | None = None
    quote: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    truncated: bool = False
    evidence_sufficient: bool = True
    response_mode: ResponseMode = "researcher"
    answer_mode: AnswerMode = "analysis"
    session_id: UUID | None = None


# ----- Chat history schemas -----

class SessionSummary(BaseModel):
    id: UUID
    title: str
    document_ids: list[str]
    response_mode: ResponseMode
    last_message_preview: str | None
    created_at: datetime
    updated_at: datetime


class SessionMessage(BaseModel):
    id: UUID
    session_id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    evidence_sufficient: bool | None = None
    response_mode: ResponseMode | None = None
    created_at: datetime


class SessionDetail(BaseModel):
    id: UUID
    title: str
    document_ids: list[str]
    response_mode: ResponseMode
    messages: list[SessionMessage]
    created_at: datetime
    updated_at: datetime


class SessionRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class DocumentChunkRead(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    text_preview: str
