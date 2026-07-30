from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.modules.chat.rag.graph.state import AnswerMode, ResponseMode

# Which retrieval tier actually supplied the evidence behind the final
# answer: "internal" (documents selected for this conversation), "full_corpus"
# (the rest of the shared library), or "web" (a live web search). None means
# no tier produced sufficient evidence this turn.
EvidenceSource = Literal["internal", "full_corpus", "web"]


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
    # Set (overwritten) by a search tool only when it returns
    # evidence_sufficient=True — always reflects the most recent tier that
    # actually justified an answer, since the ReAct loop escalates in order
    # (internal -> full_corpus -> web) and any later success supersedes an
    # earlier one. None if nothing this turn was ever sufficient.
    evidence_source: NotRequired[EvidenceSource | None]
    # Overwritten by every search tool call (success or failure) with that
    # call's `reason` — used to explain an insufficient-evidence refusal even
    # though no citations were ever recorded for it.
    last_evidence_reason: NotRequired[str | None]
    resolved_model: NotRequired[str | None]
    # The chat_messages row created up front for this turn (see
    # history_repository.create_pending_message) — carried in state so a
    # resumed turn (after an ask_user/confirm_import interrupt) keeps
    # updating the same row instead of starting a new one.
    assistant_message_id: NotRequired[str | None]
