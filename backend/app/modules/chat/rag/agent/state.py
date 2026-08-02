from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.modules.chat.rag.graph.state import AnswerMode, ResponseMode

# Which retrieval tier(s) actually supplied evidence behind the final answer:
# "internal" (documents selected for this conversation), "full_corpus" (the
# rest of the shared library), or "web" (a live web search). Usually a single
# tier (the ReAct loop escalates and stops at the first one that succeeds),
# but a comparison question ("check the web against my selected documents")
# can deliberately use more than one — see the AGENT_STRATEGY_PROMPT branch
# for that. An empty list means no tier produced sufficient evidence.
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


def add_evidence_sources(
    existing: list[EvidenceSource] | None, new: list[EvidenceSource] | None
) -> list[EvidenceSource]:
    """Merge newly-succeeded tier(s) into the running list for this turn,
    de-duplicated, preserving the order they first succeeded in (internal
    before full_corpus before web, per the escalation order search tools are
    called in — see AGENT_STRATEGY_PROMPT).

    NOT a LangGraph channel reducer — deliberately a plain helper that each
    search tool calls itself (reading the current value via
    InjectedState("evidence_sources"), same as tool_call_counts) and returns
    as a full replacement update. A real reducer channel only ever merges,
    so router.py's per-turn `"evidence_sources": []` reset on graph_input
    would silently no-op instead of clearing anything.
    """
    existing = existing or []
    merged = list(existing)
    for source in new or []:
        if source not in merged:
            merged.append(source)
    return merged


def merge_turn_citation_keys(
    existing: list[list] | None, new_citations: list[dict] | None
) -> list[list]:
    """Extend the running set of citation identities already claimed by some
    tier THIS turn (see AgentState.turn_citation_keys for why this exists).

    Stored as lists rather than tuples because the checkpointer round-trips
    state through JSON — a tuple written this turn comes back as a list on
    the next tool call, so callers must re-`tuple()` before comparing against
    a freshly computed citation_key(). Same plain-LastValue-helper shape as
    add_evidence_sources, for the same per-turn-reset reason.
    """
    existing = existing or []
    merged = [list(key) for key in existing]
    seen = {tuple(key) for key in existing}
    for citation in new_citations or []:
        key = citation_key(citation)
        if key not in seen:
            seen.add(key)
            merged.append(list(key))
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
    # Plain LastValue list (see add_evidence_sources for why this is not a
    # reducer channel), merged into by a search tool only when it returns
    # evidence_sufficient=True AND at least one of its citations is not
    # already claimed by turn_citation_keys — i.e. some OTHER tier hasn't
    # already surfaced the exact same chunk/URL earlier this same turn. A
    # full_corpus/web call that just re-finds a chunk an earlier tier already
    # cited THIS turn contributed nothing new, so it shouldn't count as a
    # distinct source — but a citation that's merely a repeat from a PRIOR
    # turn's conversation still counts, since it's genuinely being used to
    # answer the current question. Every tier that actually contributed
    # evidence this turn, not just the last one, so a deliberate multi-tier
    # comparison answer (see AGENT_STRATEGY_PROMPT) isn't misreported as
    # single-source. Empty if nothing this turn contributed.
    evidence_sources: NotRequired[list[EvidenceSource]]
    # Citation identities (citation_key() tuples, JSON-round-tripped as
    # lists — see merge_turn_citation_keys) already claimed by some tier THIS
    # turn. Reset to [] per new question exactly like evidence_sources (see
    # router.py's graph_input) so cross-turn reuse of the same chunk is never
    # penalized, only same-turn cross-tier duplication.
    turn_citation_keys: NotRequired[list[list]]
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
