from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.modules.chat.rag.graph.state import AnswerMode, ResponseMode


def citation_key(citation: dict) -> tuple:
    """Identity of a citation: a document chunk (document_id + chunk_id) or a
    live web result (source_url) — whichever of those the tool result carried.

    Shared with agent/tools.py, which numbers each tool result's citations
    against this same identity *before* they reach this reducer — a tool call
    has no other way to know the running [N] total from earlier calls in the
    same turn, and letting the model guess numbers causes exactly the citation
    mismatch this was built to prevent (see agent/tools.py::_number_citations).
    """
    return (citation.get("document_id"), citation.get("chunk_id"), citation.get("source_url"))


def add_citations(existing: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Reducer: append newly-surfaced citations, de-duplicated by identity."""
    existing = existing or []
    merged = list(existing)
    seen = {citation_key(c) for c in existing}
    for citation in new or []:
        key = citation_key(citation)
        if key in seen:
            continue
        seen.add(key)
        merged.append(citation)
    return merged


class AgentState(TypedDict):
    """State for the web-search tool-calling agent loop.

    Unlike PDFQAState (the classic single-pass RAG graph), this graph is a
    real agent_node <-> tools_node loop: `messages` accumulates the full
    tool-calling trace, and `citations` accumulates every source the agent's
    tools actually surfaced, in order of first appearance, for the final SSE
    citations payload.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    document_ids: NotRequired[list[str]]
    filenames: NotRequired[list[str]]
    model: NotRequired[str | None]
    response_mode: NotRequired[ResponseMode]
    answer_mode: NotRequired[AnswerMode]
    top_k: NotRequired[int]
    include_restricted: NotRequired[bool]
    is_admin: NotRequired[bool]
    user_id: NotRequired[str]
    tool_call_counts: NotRequired[dict[str, int]]
    last_tool_call: NotRequired[dict]
    citations: Annotated[list[dict], add_citations]
    resolved_model: NotRequired[str | None]
