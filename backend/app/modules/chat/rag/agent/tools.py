from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from app.modules.chat.rag.agent.state import (
    EvidenceSource,
    add_evidence_sources,
    citation_key,
    merge_turn_citation_keys,
)
from app.modules.chat.rag.agent_tools import web_evidence
from app.modules.documents.web_import import WebImportRequest, web_import_service
from app.modules.retrieval.contracts import MetadataFilters, RetrievalRequest
from app.modules.retrieval.service import retrieval_service
from app.modules.web_search.contracts import WebSearchProviderError
from app.modules.web_search.service import web_search_service

logger = logging.getLogger(__name__)

_cosine_distance = web_evidence.cosine_distance
_chunk_web_result_text = web_evidence.chunk_web_result_text
_score_web_results = web_evidence.score_web_results

# Repeated on every sufficient result, not just stated once in the system
# prompt: some models (verified with deepseek-chat) keep re-searching "for
# more detail/corroboration" even when the system prompt explicitly says not
# to — a reminder attached right next to the decision point measurably cuts
# that down, where the same wording living only in the system prompt did not.
SUFFICIENT_EVIDENCE_REMINDER = (
    "This is enough to answer. Your next tool call should be "
    "prepare_final_answer — do not search again just for more detail or "
    "corroboration."
)


def _tool_message(tool_call_id: str, payload: dict) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload, default=str), tool_call_id=tool_call_id)


def _number_citations(
    existing: list[dict], candidates: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Assign each candidate the exact [N] number it will have once merged.

    A tool call has no way to know the running citation total from earlier
    calls in the same turn — the model would otherwise have to guess numbers,
    which is exactly what caused citation markers to point at the wrong
    source (e.g. a [4] the model meant as a web result landing on an
    unrelated PDF chunk instead). `existing` is this turn's already-numbered
    citations (via InjectedState); duplicates reuse their existing number,
    genuinely new ones get the next free number in order.

    Returns (numbered_results_for_the_model, brand_new_citations_to_merge).
    """
    existing_numbers = {citation_key(c): c.get("number") for c in existing}
    numbered_results: list[dict] = []
    new_citations: list[dict] = []
    seen_this_call: set = set()
    next_number = len(existing) + 1
    for candidate in candidates:
        key = citation_key(candidate)
        if key in existing_numbers:
            numbered_results.append({**candidate, "number": existing_numbers[key]})
            continue
        if key in seen_this_call:
            continue
        seen_this_call.add(key)
        numbered = {**candidate, "number": next_number}
        numbered_results.append(numbered)
        new_citations.append(numbered)
        next_number += 1
    return numbered_results, new_citations


def _results_with_evidence_text(
    numbered_results: list[dict],
    evidence_items: list[dict],
) -> list[dict]:
    """Give the Agent full evidence while keeping persisted quotes compact.

    Citation objects intentionally store a 500-character quote for API/history
    payloads. Tool results need the complete retrieved chunk, otherwise the
    writer can falsely conclude that facts later in the same chunk are absent.
    """

    by_chunk = {
        str(item.get("chunk_id")): item.get("text", "")
        for item in evidence_items
        if item.get("chunk_id")
    }
    by_url = {
        item.get("url") or item.get("source_url"): item.get("text", "")
        for item in evidence_items
        if item.get("url") or item.get("source_url")
    }
    return [
        {
            **result,
            "text": by_chunk.get(str(result.get("chunk_id")))
            or by_url.get(result.get("source_url"))
            or result.get("quote", ""),
        }
        for result in numbered_results
    ]


def _claims_new_ground(turn_citation_keys: list[list] | None, raw_citations: list[dict]) -> bool:
    """True if at least one of this call's citations is not already claimed
    by an earlier tier THIS turn (see AgentState.turn_citation_keys) — i.e.
    this tier is telling us something no other tier already established this
    turn, as opposed to just re-finding the same chunk/URL a different tier
    already searched up.
    """
    claimed = {tuple(key) for key in (turn_citation_keys or [])}
    return any(citation_key(c) not in claimed for c in raw_citations)


def _run_retrieval_pipeline(
    question: str,
    identifiers: list[str],
    *,
    top_k: int,
    include_restricted: bool,
    metadata_filters: dict | None = None,
) -> dict:
    """Compatibility adapter around the shared selected-document retriever."""
    return retrieval_service.retrieve(
        RetrievalRequest(
            question=question,
            scope="selected",
            identifiers=tuple(identifiers),
            top_k=top_k,
            include_restricted=include_restricted,
            metadata_filters=MetadataFilters.from_mapping(metadata_filters),
        )
    ).as_state()


@tool
async def search_internal_documents(
    query: str,
    decision_reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    document_ids: Annotated[list[str], InjectedState("document_ids")],
    filenames: Annotated[list[str], InjectedState("filenames")],
    top_k: Annotated[int, InjectedState("top_k")],
    include_restricted: Annotated[bool, InjectedState("include_restricted")],
    citations: Annotated[list[dict], InjectedState("citations")],
    evidence_sources: Annotated[list[EvidenceSource], InjectedState("evidence_sources")],
    turn_citation_keys: Annotated[list[list], InjectedState("turn_citation_keys")],
    metadata_filters: Annotated[dict, InjectedState("metadata_filters")],
    reflection_on_previous_result: str | None = None,
) -> Command:
    """Search only the documents selected for this conversation.

    The result includes `evidence_sufficient` — computed by the same
    deterministic cosine-distance/reranker gate the classic answer path
    uses, not your own judgement — telling you whether these documents
    actually support an answer. Each result has a `number`: cite it with
    exactly that [N], never a guessed or recomputed one. Briefly state why
    you chose this action in `decision_reason`; it is shown as a concise UI
    trace, not hidden reasoning. If this is not your first tool call this
    turn, also fill `reflection_on_previous_result` — see its own
    description for what goes there.

    You may call this at most five times per turn for distinct sub-topics or
    materially different query reformulations. Stop as soon as a call is
    sufficient. In particular, split a query that bundled multiple
    sub-topics into one string, which dilutes the match and can make
    documents that do have the answer look insufficient.
    """
    identifiers = document_ids or filenames or []

    def _run() -> dict:
        return _run_retrieval_pipeline(
            query,
            identifiers,
            top_k=top_k or 8,
            include_restricted=include_restricted,
            metadata_filters=metadata_filters,
        )

    result = await asyncio.to_thread(_run)
    sufficient = result.get("evidence_sufficient", False)
    raw_citations = [
        dict(c, source_type="document", tier="internal") for c in result.get("citations", [])
    ]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    tool_results = _results_with_evidence_text(
        numbered_results,
        result.get("chunks", []),
    )
    payload = {
        "evidence_sufficient": sufficient,
        "reason": result.get("evidence_reason"),
        "results": tool_results,
        "filter_applied": result.get("filter_applied", False),
        "filter_fallback": result.get("filter_fallback", False),
        "filter_notice": result.get("filter_notice"),
    }
    if sufficient:
        payload["reminder"] = SUFFICIENT_EVIDENCE_REMINDER
    update: dict = {
        "messages": [_tool_message(tool_call_id, payload)],
        "citations": new_citations,
        "last_evidence_reason": result.get("evidence_reason"),
        "filter_fallback": result.get("filter_fallback", False),
        "filter_notice": result.get("filter_notice"),
    }
    # Only credit this tier if it actually surfaced evidence no other tier
    # already claimed THIS turn — a full_corpus/web call that just re-finds a
    # chunk already cited via an earlier tier this turn contributed nothing
    # new, so it shouldn't light up that tier's "From the ..." badge. Reusing
    # a chunk cited in a PRIOR turn still counts (turn_citation_keys resets
    # every new question) since it's genuinely evidence for this answer.
    if sufficient and _claims_new_ground(turn_citation_keys, raw_citations):
        update["evidence_sources"] = add_evidence_sources(evidence_sources, ["internal"])
        update["turn_citation_keys"] = merge_turn_citation_keys(turn_citation_keys, raw_citations)
    return Command(update=update)


@tool
async def search_full_corpus(
    query: str,
    decision_reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    top_k: Annotated[int, InjectedState("top_k")],
    include_restricted: Annotated[bool, InjectedState("include_restricted")],
    citations: Annotated[list[dict], InjectedState("citations")],
    evidence_sources: Annotated[list[EvidenceSource], InjectedState("evidence_sources")],
    turn_citation_keys: Annotated[list[list], InjectedState("turn_citation_keys")],
    metadata_filters: Annotated[dict, InjectedState("metadata_filters")],
    reflection_on_previous_result: str | None = None,
) -> Command:
    """Search the ENTIRE document library, not just documents selected for
    this conversation.

    Each result has a `number`: cite it with exactly that [N], never a
    guessed or recomputed one. The ReAct loop allows at most five calls per
    turn for distinct sub-topics or materially different reformulations;
    stop as soon as a call is sufficient. Briefly state why you chose this
    action in `decision_reason`. If this is not your first tool call this
    turn, also fill `reflection_on_previous_result` — see its own description
    for what goes there.
    """

    def _run():
        return retrieval_service.retrieve(
            RetrievalRequest(
                question=query,
                scope="full_corpus",
                top_k=top_k or 8,
                include_restricted=include_restricted,
                metadata_filters=MetadataFilters.from_mapping(metadata_filters),
            )
        )

    result = await asyncio.to_thread(_run)
    sufficient = result.evidence.sufficient
    reason = result.evidence.reason
    raw_citations = [
        dict(citation, source_type="document", tier="full_corpus")
        for citation in result.citations
    ]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    tool_results = _results_with_evidence_text(numbered_results, result.chunks)
    payload = {
        "evidence_sufficient": sufficient,
        "reason": reason,
        "results": tool_results,
        "filter_applied": result.filter_applied,
        "filter_fallback": result.filter_fallback,
        "filter_notice": result.filter_notice,
    }
    if sufficient:
        payload["reminder"] = SUFFICIENT_EVIDENCE_REMINDER
    update: dict = {
        "messages": [_tool_message(tool_call_id, payload)],
        "citations": new_citations,
        "last_evidence_reason": reason,
        "filter_fallback": result.filter_fallback,
        "filter_notice": result.filter_notice,
    }
    # See search_internal_documents above: only credit this tier when it
    # contributed a citation no other tier already claimed this turn.
    if sufficient and _claims_new_ground(turn_citation_keys, raw_citations):
        update["evidence_sources"] = add_evidence_sources(evidence_sources, ["full_corpus"])
        update["turn_citation_keys"] = merge_turn_citation_keys(turn_citation_keys, raw_citations)
    return Command(update=update)


@tool
def ask_user(
    question: str,
    decision_reason: str,
    mode: Literal["confirm", "choice", "freeform"] = "confirm",
    options: list[str] | None = None,
    reflection_on_previous_result: str | None = None,
) -> str:
    """Pause the run and ask the user a question, resuming with their answer
    once given.

    Three modes:
    - "confirm": a yes/no gate. `options` defaults to ["Yes", "No"].
    - "choice": 2+ concrete options you found plausible (e.g. candidate
      documents, countries, or time periods) for the user to disambiguate.
      Requires at least 2 `options`.
    - "freeform": an open clarifying question with no fixed options;
      `options` is ignored.

    The UI always lets the user type their own answer instead of picking a
    listed option, so the returned string is not guaranteed to equal any
    option you offered — read it for intent, not exact match. Briefly state
    why confirmation is needed in `decision_reason`. If this is not your
    first tool call this turn, also fill `reflection_on_previous_result` —
    see its own description for what goes there.
    """
    if mode == "choice" and len(options or []) < 2:
        return json.dumps(
            {
                "error": "mode='choice' requires at least 2 options.",
                "hint": "Pass 2+ options, or use mode='freeform' for an open question.",
            }
        )
    if mode == "confirm":
        effective_options = options or ["Yes", "No"]
    elif mode == "choice":
        effective_options = options
    else:
        effective_options = None
    answer = interrupt(
        {"type": "ask_user", "mode": mode, "question": question, "options": effective_options}
    )
    return str(answer)


@tool
def prepare_final_answer(
    answer_plan: str,
    citation_numbers: list[int] | None,
    tool_call_id: Annotated[str, InjectedToolCallId],
    reflection_on_previous_result: str | None = None,
) -> Command:
    """Finish the ReAct research loop and hand off to the streaming answer writer.

    Call this only when no more tools or user input are needed. The answer
    plan should briefly state what the final answer must say. Citation
    numbers must be exact source numbers already returned by search tools.
    Do not put the final prose answer in this tool call: a separate
    generation node writes and streams it to the user. If this is not your
    first tool call this turn, also fill `reflection_on_previous_result` —
    see its own description for what goes there.
    """
    payload = {
        "ready": True,
        "answer_plan": answer_plan,
        "citation_numbers": citation_numbers or [],
    }
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(payload, default=str),
                    tool_call_id=tool_call_id,
                    name="prepare_final_answer",
                )
            ]
        }
    )


@tool
async def search_web(
    query: str,
    decision_reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    citations: Annotated[list[dict], InjectedState("citations")],
    evidence_sources: Annotated[list[EvidenceSource], InjectedState("evidence_sources")],
    turn_citation_keys: Annotated[list[list], InjectedState("turn_citation_keys")],
    reflection_on_previous_result: str | None = None,
) -> Command:
    """Search the public web. Results are checked against the same
    relevance gate as document evidence (cosine distance + reranker score)
    before being usable as citations.

    Each result has a `number`: cite it with exactly that [N], never a
    guessed or recomputed one. Briefly state why web search is the next
    action in `decision_reason`. If this is not your first tool call this
    turn, also fill `reflection_on_previous_result` — see its own
    description for what goes there.
    """
    try:
        results = await web_search_service.search(query, limit=5)
    except WebSearchProviderError as exc:
        payload = {"evidence_sufficient": False, "reason": str(exc), "results": []}
        return Command(
            update={
                "messages": [_tool_message(tool_call_id, payload)],
                "last_evidence_reason": str(exc),
            }
        )

    sufficient, reason, candidates = await asyncio.to_thread(_score_web_results, query, results)
    raw_citations = [
        {
            "title": c["title"],
            "source_url": c["url"],
            "quote": c["text"][:500],
            "source_type": "web",
            "tier": "web",
        }
        for c in candidates
        if c["passed"]
    ]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    tool_results = _results_with_evidence_text(numbered_results, candidates)
    payload = {"evidence_sufficient": sufficient, "reason": reason, "results": tool_results}
    if sufficient:
        payload["reminder"] = SUFFICIENT_EVIDENCE_REMINDER
    update: dict = {
        "messages": [_tool_message(tool_call_id, payload)],
        "citations": new_citations,
        "last_evidence_reason": reason,
    }
    # See search_internal_documents above: only credit this tier when it
    # contributed a citation no other tier already claimed this turn.
    if sufficient and _claims_new_ground(turn_citation_keys, raw_citations):
        update["evidence_sources"] = add_evidence_sources(evidence_sources, ["web"])
        update["turn_citation_keys"] = merge_turn_citation_keys(turn_citation_keys, raw_citations)
    return Command(update=update)


@tool
async def import_web_page(
    url: str,
    title: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    is_admin: Annotated[bool, InjectedState("is_admin")],
    user_id: Annotated[str, InjectedState("user_id")],
    citations: Annotated[list[dict], InjectedState("citations")],
    reflection_on_previous_result: str | None = None,
) -> Command:
    """Permanently import a web page into the shared knowledge base so every
    user can find it later via search_internal_documents/search_full_corpus.

    ADMIN ONLY. Always confirm with the user first — this asks its own
    confirmation question, separate from the one-off web-search confirmation,
    because it permanently changes the shared library rather than answering
    a single question. If this is not your first tool call this turn, also
    fill `reflection_on_previous_result` — see its own description for what
    goes there.
    """
    if not is_admin:
        payload = {
            "imported": False,
            "error": "Only admins can import pages into the knowledge base.",
        }
        return Command(update={"messages": [_tool_message(tool_call_id, payload)]})

    confirmed = interrupt(
        {
            "type": "confirm_import",
            "url": url,
            "title": title,
            "question": f"Import '{title}' ({url}) into the shared knowledge base?",
        }
    )
    if not confirmed:
        payload = {"imported": False, "reason": "The user declined the import."}
        return Command(update={"messages": [_tool_message(tool_call_id, payload)]})

    try:
        result = await web_import_service.import_page(
            WebImportRequest(
                url=url,
                title=title,
                imported_by=user_id,
                imported_via="web_search",
            )
        )
    except (ValueError, WebSearchProviderError) as exc:
        payload = {"imported": False, "error": str(exc)}
        return Command(update={"messages": [_tool_message(tool_call_id, payload)]})
    document = result.document
    raw_citation = {
        "document_id": document["id"],
        "title": result.title,
        "source_url": result.source_url,
        "source_type": "document",
        "tier": "full_corpus",
    }
    numbered_results, new_citations = _number_citations(citations, [raw_citation])
    payload = {
        "imported": True,
        "was_duplicate": result.was_duplicate,
        "document_id": document["id"],
        "title": raw_citation["title"],
        "number": numbered_results[0]["number"],
    }
    return Command(
        update={
            "messages": [_tool_message(tool_call_id, payload)],
            "citations": new_citations,
        }
    )


ALL_TOOLS = [
    search_internal_documents,
    search_full_corpus,
    ask_user,
    prepare_final_answer,
    search_web,
    import_web_page,
]
