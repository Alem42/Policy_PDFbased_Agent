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
from app.modules.chat.rag.evidence import (
    assess_evidence_sufficiency,
    max_vector_distance,
    min_reranker_score,
)
from app.modules.chat.rag.graph.nodes import (
    check_evidence_node,
    load_documents_node,
    retrieve_context_node,
)
from app.modules.chat.rag.graph.state import PDFQAState
from app.modules.chat.rag.web_search.contracts import WebSearchProviderError, WebSearchResult
from app.modules.chat.rag.web_search.registry import get_active_web_search_provider
from app.modules.documents.chunker import TiktokenDocumentChunker
from app.modules.documents.embeddings import embed_documents, embed_query
from app.modules.documents.service import save_web_import
from app.modules.documents.service import search_full_corpus as search_full_corpus_service
from app.modules.reranking.service import enabled as reranker_enabled
from app.modules.reranking.service import rerank as rerank_chunks

logger = logging.getLogger(__name__)

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


def _document_citation(chunk: dict) -> dict:
    return {
        "document_id": chunk.get("document_id"),
        "title": chunk.get("doc_title") or chunk.get("file"),
        "chunk_id": chunk.get("chunk_id"),
        "page": chunk.get("page_start") or chunk.get("page"),
        "quote": (chunk.get("text") or "")[:500],
        "source_type": "document",
        # Which EvidenceSource tier found this (see agent/state.py) — router.py
        # uses this to report only the tier(s) the final answer actually cites,
        # not every tier that merely surfaced a candidate during the loop.
        "tier": "full_corpus",
    }


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
) -> dict:
    """Load pages + retrieve + evidence-check for a set of documents.

    This is exactly what workflow.run_retrieval() does — reused directly so
    the agent's evidence gate is the same deterministic code the classic RAG
    answer path uses, not a re-implementation the LLM has to trust.
    """
    state: PDFQAState = {
        "question": question,
        "document_ids": identifiers,
        "filenames": [],
        "model": None,
        "top_k": top_k,
        "include_restricted": include_restricted,
    }
    state.update(load_documents_node(state))
    state.update(retrieve_context_node(state))
    state.update(check_evidence_node(state))
    return dict(state)


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
            query, identifiers, top_k=top_k or 8, include_restricted=include_restricted
        )

    result = await asyncio.to_thread(_run)
    sufficient = result.get("evidence_sufficient", False)
    raw_citations = [
        dict(c, source_type="document", tier="internal") for c in result.get("citations", [])
    ]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    payload = {
        "evidence_sufficient": sufficient,
        "reason": result.get("evidence_reason"),
        "results": numbered_results,
    }
    if sufficient:
        payload["reminder"] = SUFFICIENT_EVIDENCE_REMINDER
    update: dict = {
        "messages": [_tool_message(tool_call_id, payload)],
        "citations": new_citations,
        "last_evidence_reason": result.get("evidence_reason"),
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

    def _run() -> tuple[bool, str | None, list[dict]]:
        chunks = search_full_corpus_service(
            query, limit=top_k or 8, include_restricted=include_restricted
        )
        threshold = max_vector_distance()
        relevant = [c for c in chunks if float(c.get("distance", 1.0)) <= threshold]
        context = "\n\n".join(c.get("text", "") for c in relevant)
        sufficient, reason = assess_evidence_sufficiency(
            question=query,
            raw_chunks=chunks,
            pages=[],
            context=context,
            has_embeddings=True,
        )
        return sufficient, reason, relevant

    sufficient, reason, relevant = await asyncio.to_thread(_run)
    raw_citations = [_document_citation(c) for c in relevant]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    payload = {"evidence_sufficient": sufficient, "reason": reason, "results": numbered_results}
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


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1 - dot / (norm_a * norm_b)


# Tiktoken-based (no live embedding-config/DB lookup), unlike the
# EmbeddingModelDocumentChunker document ingestion uses — splitting a web
# result into retrieval-sized pieces doesn't need to match the admin-tunable
# ingestion budget exactly, and staying DB-free keeps this a pure, fast helper.
_web_result_chunker = TiktokenDocumentChunker()


def _chunk_web_result_text(text: str) -> list[str]:
    """Split one page's content into retrieval-sized pieces before embedding.

    Firecrawl's search() requests full-page markdown per hit, not a short
    excerpt (see web_search/providers/firecrawl.py), so embedding a whole
    page as one vector blurs together everything on it and risks silently
    exceeding the reranker's own max input length. Reuse the same chunker
    document ingestion uses instead of a page-sized vector.
    """
    clean = text.strip()
    if not clean:
        return []
    chunks = _web_result_chunker.chunk([{"page": 1, "text": clean}])
    return [c["text"] for c in chunks] or [clean]


def _score_web_results(
    query: str, results: list[WebSearchResult]
) -> tuple[bool, str | None, list[dict]]:
    """Apply the SAME evidence gate as document chunks: cosine distance, then
    reranker score. Each result is chunked first so a long page is judged by
    its single best-matching chunk, not one oversized whole-page vector.
    Only results that pass both are usable citations."""
    if not results:
        return False, "The web search returned no results.", []

    owners: list[int] = []
    texts: list[str] = []
    for index, result in enumerate(results):
        for chunk_text in _chunk_web_result_text(result.content or result.title):
            owners.append(index)
            texts.append(chunk_text)

    if not texts:
        return False, "The web search returned no usable content.", []

    query_vector = embed_query(query)
    chunk_vectors = embed_documents(texts)

    # Collapse per-chunk scores back to one candidate per URL: the chunk
    # closest to the query represents that page as a citation.
    best_per_result: dict[int, dict] = {}
    for owner, text, vector in zip(owners, texts, chunk_vectors, strict=True):
        distance = _cosine_distance(query_vector, vector)
        current = best_per_result.get(owner)
        if current is None or distance < current["distance"]:
            best_per_result[owner] = {
                "title": results[owner].title,
                "url": results[owner].url,
                "text": text,
                "distance": distance,
                "passed": False,
            }
    candidates = [best_per_result[i] for i in range(len(results)) if i in best_per_result]

    threshold = max_vector_distance()
    relevant = [c for c in candidates if c["distance"] <= threshold]
    if not relevant:
        return False, "No web result was close enough to the question.", candidates

    if reranker_enabled():
        try:
            reranked = rerank_chunks(query, relevant, limit=len(relevant))
            best_score = max((c.get("reranker_score", min_reranker_score())) for c in reranked)
            if best_score < min_reranker_score():
                return False, "No web result passed the relevance reranker.", candidates
            relevant = reranked
        except Exception:
            logger.exception("Reranking web search results failed; using cosine ranking only.")

    passed_urls = {c["url"] for c in relevant}
    for candidate in candidates:
        candidate["passed"] = candidate["url"] in passed_urls
    return True, None, candidates


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
    provider = get_active_web_search_provider()
    try:
        results = await provider.search(query, limit=5)
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
    payload = {"evidence_sufficient": sufficient, "reason": reason, "results": numbered_results}
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

    provider = get_active_web_search_provider()
    try:
        page = await provider.fetch_page(url)
    except WebSearchProviderError as exc:
        payload = {"imported": False, "error": str(exc)}
        return Command(update={"messages": [_tool_message(tool_call_id, payload)]})

    document, was_duplicate = await save_web_import(
        url=page.url or url,
        title=page.title or title,
        markdown=page.content,
        imported_by=user_id,
        imported_via="web_search",
    )
    raw_citation = {
        "document_id": document["id"],
        "title": document.get("title") or document.get("name"),
        "source_url": document.get("source_url") or page.url or url,
        "source_type": "document",
        "tier": "full_corpus",
    }
    numbered_results, new_citations = _number_citations(citations, [raw_citation])
    payload = {
        "imported": True,
        "was_duplicate": was_duplicate,
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
