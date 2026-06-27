from typing import NotRequired, TypedDict


class PDFQAState(TypedDict):
    """Shared state passed between LangGraph nodes."""

    question: str
    document_ids: NotRequired[list[str]]
    filenames: NotRequired[list[str]]
    model: str | None
    top_k: NotRequired[int]
    include_restricted: NotRequired[bool]
    pages: NotRequired[list[dict]]
    chunks: NotRequired[list[dict]]
    citations: NotRequired[list[dict]]
    context: NotRequired[str]
    truncated: NotRequired[bool]
    answer: NotRequired[str]
