from typing import Literal, NotRequired, TypedDict

ResponseMode = Literal["researcher", "student"]


class PDFQAState(TypedDict):
    """Shared state passed between LangGraph nodes."""

    question: str
    document_ids: NotRequired[list[str]]
    filenames: NotRequired[list[str]]
    model: str | None
    response_mode: NotRequired[ResponseMode]
    top_k: NotRequired[int]
    include_restricted: NotRequired[bool]
    history: NotRequired[list[dict]]  # [{"role": "user"|"assistant", "content": str}, ...]
    pages: NotRequired[list[dict]]
    chunks: NotRequired[list[dict]]
    citations: NotRequired[list[dict]]
    context: NotRequired[str]
    truncated: NotRequired[bool]
    used_vector_retrieval: NotRequired[bool]
    evidence_sufficient: NotRequired[bool]
    evidence_reason: NotRequired[str | None]
    answer: NotRequired[str]
