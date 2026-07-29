from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from app.modules.chat.rag.agent.state import citation_key
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
from app.modules.documents.embeddings import embed_documents, embed_query
from app.modules.documents.service import save_web_import
from app.modules.documents.service import search_full_corpus as search_full_corpus_service
from app.modules.reranking.service import enabled as reranker_enabled
from app.modules.reranking.service import rerank as rerank_chunks

logger = logging.getLogger(__name__)


def _document_citation(chunk: dict) -> dict:
    return {
        "document_id": chunk.get("document_id"),
        "title": chunk.get("doc_title") or chunk.get("file"),
        "chunk_id": chunk.get("chunk_id"),
        "page": chunk.get("page_start") or chunk.get("page"),
        "quote": (chunk.get("text") or "")[:500],
        "source_type": "document",
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
    tool_call_id: Annotated[str, InjectedToolCallId],
    document_ids: Annotated[list[str], InjectedState("document_ids")],
    filenames: Annotated[list[str], InjectedState("filenames")],
    top_k: Annotated[int, InjectedState("top_k")],
    include_restricted: Annotated[bool, InjectedState("include_restricted")],
    citations: Annotated[list[dict], InjectedState("citations")],
) -> Command:
    """Search only the documents selected for this conversation.

    Always call this first, before any other search tool. The result
    includes `evidence_sufficient` — computed by the same deterministic
    cosine-distance/reranker gate the classic answer path uses, not your own
    judgement — telling you whether these documents actually support an
    answer. Each result has a `number`: cite it with exactly that [N], never
    a guessed or recomputed one.
    """
    identifiers = document_ids or filenames or []

    def _run() -> dict:
        return _run_retrieval_pipeline(
            query, identifiers, top_k=top_k or 8, include_restricted=include_restricted
        )

    result = await asyncio.to_thread(_run)
    raw_citations = [dict(c, source_type="document") for c in result.get("citations", [])]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    payload = {
        "evidence_sufficient": result.get("evidence_sufficient", False),
        "reason": result.get("evidence_reason"),
        "results": numbered_results,
    }
    return Command(
        update={
            "messages": [_tool_message(tool_call_id, payload)],
            "citations": new_citations,
        }
    )


@tool
async def search_full_corpus(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    top_k: Annotated[int, InjectedState("top_k")],
    include_restricted: Annotated[bool, InjectedState("include_restricted")],
    citations: Annotated[list[dict], InjectedState("citations")],
) -> Command:
    """Search the ENTIRE document library, not just documents selected for
    this conversation.

    Only call this after search_internal_documents reports
    evidence_sufficient=false — e.g. another user may have already imported
    relevant material into the shared library. Each result has a `number`:
    cite it with exactly that [N], never a guessed or recomputed one.
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
    return Command(
        update={
            "messages": [_tool_message(tool_call_id, payload)],
            "citations": new_citations,
        }
    )


@tool
def ask_user(question: str, options: list[str] | None = None) -> str:
    """Pause and ask the user to confirm whether to search the public web.

    Use this when internal documents don't have enough evidence and the
    user's message did not already make clear they want a web search — do
    NOT use it if the user already said things like "search the web" /
    "look it up online" (go straight to search_web instead).
    """
    answer = interrupt(
        {"type": "confirm_websearch", "question": question, "options": options or ["Yes", "No"]}
    )
    return str(answer)


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1 - dot / (norm_a * norm_b)


def _score_web_results(
    query: str, results: list[WebSearchResult]
) -> tuple[bool, str | None, list[dict]]:
    """Apply the SAME evidence gate as document chunks: cosine distance, then
    reranker score. Only results that pass both are usable citations."""
    if not results:
        return False, "The web search returned no results.", []

    texts = [r.content or r.title for r in results]
    query_vector = embed_query(query)
    doc_vectors = embed_documents(texts)
    threshold = max_vector_distance()

    candidates = [
        {
            "title": result.title,
            "url": result.url,
            "text": text,
            "distance": _cosine_distance(query_vector, vector),
            "passed": False,
        }
        for result, text, vector in zip(results, texts, doc_vectors, strict=True)
    ]

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
    tool_call_id: Annotated[str, InjectedToolCallId],
    citations: Annotated[list[dict], InjectedState("citations")],
) -> Command:
    """Search the public web. Results are checked against the same
    relevance gate as document evidence (cosine distance + reranker score)
    before being usable as citations.

    Only call this after search_internal_documents AND search_full_corpus
    both report evidence_sufficient=false, and after the user has confirmed
    (via ask_user) or already explicitly asked for a web search. Each result
    has a `number`: cite it with exactly that [N], never a guessed or
    recomputed one.
    """
    provider = get_active_web_search_provider()
    try:
        results = await provider.search(query, limit=5)
    except WebSearchProviderError as exc:
        payload = {"evidence_sufficient": False, "reason": str(exc), "results": []}
        return Command(update={"messages": [_tool_message(tool_call_id, payload)]})

    sufficient, reason, candidates = await asyncio.to_thread(_score_web_results, query, results)
    raw_citations = [
        {
            "title": c["title"],
            "source_url": c["url"],
            "quote": c["text"][:500],
            "source_type": "web",
        }
        for c in candidates
        if c["passed"]
    ]
    numbered_results, new_citations = _number_citations(citations, raw_citations)
    payload = {"evidence_sufficient": sufficient, "reason": reason, "results": numbered_results}
    return Command(
        update={
            "messages": [_tool_message(tool_call_id, payload)],
            "citations": new_citations,
        }
    )


@tool
async def import_web_page(
    url: str,
    title: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    is_admin: Annotated[bool, InjectedState("is_admin")],
    user_id: Annotated[str, InjectedState("user_id")],
    citations: Annotated[list[dict], InjectedState("citations")],
) -> Command:
    """Permanently import a web page into the shared knowledge base so every
    user can find it later via search_internal_documents/search_full_corpus.

    ADMIN ONLY. Always confirm with the user first — this asks its own
    confirmation question, separate from the one-off web-search confirmation,
    because it permanently changes the shared library rather than answering
    a single question.
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
    search_web,
    import_web_page,
]
