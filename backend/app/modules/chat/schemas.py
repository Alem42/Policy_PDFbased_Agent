from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ResponseMode = Literal["researcher", "policymaker", "student"]
AnswerMode = Literal["analysis", "chat"]
# "react": multi-step tool-calling agent (web search, escalation, reasoning
# trace). "direct": single retrieval pass + one-shot answer, no tool loop.
AgentMode = Literal["react", "direct"]
# Which retrieval tier(s) produced the evidence behind an assistant answer.
# Usually a single entry (the ReAct loop stops at the first tier that
# succeeds), but a deliberate documents-vs-web comparison question can use
# more than one. An empty list means no tier was sufficient this turn —
# either an Open Discussion general-knowledge fallback or a Document
# Analysis refusal, told apart by answer_mode on the frontend.
EvidenceSource = Literal["internal", "full_corpus", "web"]

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
    language: str | None = None
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
    agent_mode: AgentMode = "react"
    # When session_id is provided the backend reads history from the DB directly.
    # When None a new session is created automatically.
    session_id: UUID | None = None
    # Kept for backwards-compat with clients that still send history inline.
    # DB history takes precedence when session_id is set.
    history: list[ChatMessage] = Field(default_factory=list)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Citation(BaseModel):
    document_id: UUID | None = None  # None when built from page-level fallback
    title: str
    chunk_id: UUID | None = None
    source_url: str | None = None
    page: int | None = None
    quote: str | None = None
    # "document" (selected/library/imported document chunk) or "web" (a live
    # web search result that was never imported). Defaults to "document" for
    # the classic RAG path, which never had live web results.
    source_type: Literal["document", "web"] = "document"


class ResumeChatRequest(BaseModel):
    """Resumes a chat turn that was paused by interrupt() — e.g. the user's
    answer to an ask_user or confirm_import prompt."""

    session_id: UUID
    # Whatever the interrupted tool's `interrupt()` call expects back: any
    # string (a listed option or free-typed text) for ask_user, a bool for
    # import_web_page's confirmation.
    answer: str | bool


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    truncated: bool = False
    evidence_sufficient: bool = True
    evidence_reason: str | None = None
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    response_mode: ResponseMode = "researcher"
    answer_mode: AnswerMode = "analysis"
    agent_mode: AgentMode = "direct"
    session_id: UUID | None = None
    # Resolved "<provider>/<model-id>" that actually answered, e.g. "openai/gpt-4o".
    model: str | None = None
    # Validated follow-up questions the selected documents can answer (may be empty).
    suggestions: list[str] = Field(default_factory=list)


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
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    response_mode: ResponseMode | None = None
    answer_mode: AnswerMode | None = None
    agent_mode: AgentMode | None = None
    model: str | None = None
    # The tool-call trace recorded while this message was generated (empty
    # for user messages and for turns that predate this field).
    steps: list[dict] = Field(default_factory=list)
    # 'streaming' if the turn never finished (crashed / interrupted and never
    # resumed), 'error' if it failed, 'complete' otherwise.
    status: str = "complete"
    # Validated follow-up questions generated after this answer (may be empty).
    suggestions: list[str] = Field(default_factory=list)
    # LLM tokens spent generating this turn (every ReAct decision step plus
    # the final answer writer, summed). None for user messages, direct-mode
    # answers, and turns predating this field / whose provider never
    # reported usage.
    token_usage: TokenUsage | None = None
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


class ModelOption(BaseModel):
    id: str  # "<provider>/<model-id>", e.g. "openai/gpt-4o" — pass as ChatRequest.model
    label: str


class ProviderModels(BaseModel):
    provider: str
    provider_label: str
    models: list[ModelOption]


class DocumentChunkRead(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    text_preview: str
