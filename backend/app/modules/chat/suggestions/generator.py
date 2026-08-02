"""Generate + validate follow-up question suggestions.

Approach A: the LLM proposes candidate follow-ups grounded in the answer + the
retrieved excerpts, under a strict "only questions the documents can answer" rule.

Approach D (the anti-hallucination guard the client cares about): every candidate
is retrieved against the SAME selected documents and passed through the SAME
evidence thresholds a real question would face (cosine distance + optional
reranker floor). Only questions that would NOT trigger "low evidence" survive, so
we never suggest something the corpus can't actually answer.

Fail-safe: any generation error returns [] (no chips, answer unaffected); any
candidate whose validation errors or fails is simply dropped.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.config import SuggestionConfig
from app.modules.chat.suggestions.profile import personalization_hint
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.service import resolve_document_ids
from app.modules.embedding import service as embedding
from app.modules.reranking import service as reranking
from app.modules.retrieval.evidence import max_vector_distance, min_reranker_score

logger = logging.getLogger(__name__)

# Bounds on what we feed the candidate LLM (keep the call cheap).
_MAX_ANSWER_CHARS = 2000
_MAX_CONTEXT_CHARS = 6000

CANDIDATE_SYSTEM = """You suggest follow-up questions for a document-grounded policy Q&A system.
Given the user's question, the assistant's answer, and excerpts from the user's SELECTED policy
documents, propose {n} follow-up questions the user might naturally ask next.

Strict rules:
- Every suggested question MUST be answerable using ONLY the selected document excerpts below.
- Do NOT propose questions that need information beyond these excerpts: no outside knowledge, and
  no countries, policies, figures, or time periods that do not appear in the excerpts.
- Prefer specific questions about facts, figures, mechanisms, risks, timelines, or comparisons that
  the excerpts actually contain.
- Keep each question under {max_chars} characters, natural, standalone, and non-overlapping.
- Write in the SAME LANGUAGE as the user's question.
- Do not repeat or lightly reword the user's original question.
{personalization}
Return ONLY a JSON array of strings, e.g. ["...", "..."]. No prose, no markdown, no code fences."""


def _parse_candidates(raw: str) -> list[str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    # Strict parse first: the whole text, then the first [...] block.
    blocks = [text]
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if match:
        blocks.append(match.group(0))
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]

    # Fallback: providers occasionally truncate the array before its closing "]"
    # (the strings are all complete, just the final bracket is dropped). Recover
    # every COMPLETE JSON string literal so one missing bracket doesn't cost us
    # all the suggestions; unterminated partial strings are ignored by design.
    recovered: list[str] = []
    for literal in re.findall(r'"(?:[^"\\]|\\.)*"', text):
        try:
            value = str(json.loads(literal)).strip()
        except Exception:
            continue
        if value:
            recovered.append(value)
    return recovered


def _normalize(text: str) -> str:
    """Loose key for near-duplicate detection: lowercase, alphanumerics only."""
    return re.sub(r"[^a-z0-9一-鿿]+", "", text.lower())


def _history_questions(history: list[dict] | None) -> set[str]:
    return {
        _normalize(m["content"])
        for m in (history or [])
        if m.get("role") == "user" and m.get("content")
    }


def _clean_candidates(raw_candidates: list[str], history: list[dict] | None, cfg: SuggestionConfig,
                      original_question: str) -> list[str]:
    seen = _history_questions(history)
    seen.add(_normalize(original_question))
    cleaned: list[str] = []
    for candidate in raw_candidates:
        text = candidate.strip()
        if len(text) > cfg.max_question_chars:
            text = text[: cfg.max_question_chars].rstrip()
        key = _normalize(text)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned[: cfg.candidate_pool]


def _propose_candidates(
    *,
    question: str,
    answer: str,
    context: str,
    model: str | None,
    cfg: SuggestionConfig,
    user_id: str | None,
) -> list[str]:
    hint = personalization_hint(user_id) if cfg.personalize else ""
    system = CANDIDATE_SYSTEM.format(
        n=cfg.candidate_pool,
        max_chars=cfg.max_question_chars,
        personalization=(f"- {hint}\n" if hint else ""),
    )
    human = (
        f"User question:\n{question}\n\n"
        f"Assistant answer:\n{answer[:_MAX_ANSWER_CHARS]}\n\n"
        f"Selected document excerpts:\n{context[:_MAX_CONTEXT_CHARS]}"
    )
    provider, selected_model, _ = resolve_generation_target(model)
    # Suggestions are short JSON strings, but leave enough headroom for the whole
    # array to close — too tight a cap truncates the JSON. The tolerant parser
    # (_parse_candidates) still recovers complete strings if a provider drops the
    # closing bracket anyway.
    output_budget = max(512, cfg.candidate_pool * 96)
    client = create_chat_client(
        provider,
        selected_model,
        temperature=cfg.temperature,
        max_tokens=output_budget,
    )
    response = client.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return _parse_candidates(str(response.content))


def _passes_reranker_gate(
    candidate: str,
    chunks: list[dict],
    cfg: SuggestionConfig,
) -> bool:
    """Apply the expensive secondary gate only after dense distance passes."""
    try:
        ranked = reranking.rerank(
            candidate,
            chunks[: cfg.validation_top_k],
            limit=cfg.validation_top_k,
        )
    except Exception:
        logger.exception("Reranker validation failed for candidate; dropping it")
        return False
    scores = [chunk["reranker_score"] for chunk in ranked if "reranker_score" in chunk]
    return bool(scores) and max(scores) >= min_reranker_score()


def _validated_candidates(
    candidates: list[str],
    identifiers: list[str],
    include_restricted: bool,
    cfg: SuggestionConfig,
) -> list[str]:
    """Batch dense retrieval, then progressively apply the evidence gates."""
    document_ids = resolve_document_ids(identifiers, include_restricted)
    vectors = embedding.embed_queries(candidates)
    if len(vectors) != len(candidates):
        raise RuntimeError("Embedding provider returned an unexpected query-vector count.")

    # Preserve normal RAG's wider dense recall pool, but do not send all 20
    # chunks through the expensive reranker.
    dense_limit = max(cfg.validation_top_k * 3, 20)
    dense_results = embedding_repository.retrieve_many(
        [embedding.vector_literal(vector) for vector in vectors],
        document_ids,
        limit=dense_limit,
    )
    if len(dense_results) != len(candidates):
        raise RuntimeError("Batch retrieval returned an unexpected result-group count.")

    gate_distance = cfg.effective_distance(max_vector_distance())
    distance_survivors: list[tuple[int, str, list[dict]]] = []
    for index, (candidate, chunks) in enumerate(zip(candidates, dense_results, strict=True)):
        if not chunks:
            continue
        best_distance = min(float(chunk.get("distance", 1.0)) for chunk in chunks)
        if best_distance <= gate_distance:
            distance_survivors.append((index, candidate, chunks))

    if not cfg.use_reranker_validation or not reranking.enabled():
        return [candidate for _, candidate, _ in distance_survivors][: cfg.max_suggestions]

    passed_indices: set[int] = set()
    reranker_provider = reranking.active_config().provider
    if reranker_provider == "local":
        # Local inference already batches a candidate's chunk pairs internally.
        # Keep it sequential to avoid CPU/GPU contention, stopping once enough pass.
        for index, candidate, chunks in distance_survivors:
            if _passes_reranker_gate(candidate, chunks, cfg):
                passed_indices.add(index)
            if len(passed_indices) >= cfg.max_suggestions:
                break
    else:
        # Remote APIs generally accept one query with many documents, not many
        # queries. Bound concurrency so their network latency overlaps without
        # creating a request spike.
        workers = min(3, len(distance_survivors))
        if workers:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    index: executor.submit(_passes_reranker_gate, candidate, chunks, cfg)
                    for index, candidate, chunks in distance_survivors
                }
                for index, future in futures.items():
                    if future.result():
                        passed_indices.add(index)

    return [
        candidate
        for index, candidate, _ in distance_survivors
        if index in passed_indices
    ][: cfg.max_suggestions]


def generate_followup_suggestions(
    *,
    question: str,
    answer: str,
    context: str,
    identifiers: list[str],
    response_mode: str = "researcher",
    history: list[dict] | None = None,
    include_restricted: bool = False,
    model: str | None = None,
    user_id: str | None = None,
    config: SuggestionConfig | None = None,
) -> list[str]:
    """Return up to max_suggestions validated follow-up questions ([] if disabled/failed)."""
    cfg = config or suggestions_service.active_config()
    if not cfg.enabled or not identifiers or not context.strip():
        return []

    try:
        raw = _propose_candidates(
            question=question,
            answer=answer,
            context=context,
            model=model,
            cfg=cfg,
            user_id=user_id,
        )
    except Exception:
        logger.exception("Follow-up candidate generation failed")
        return []

    candidates = _clean_candidates(raw, history, cfg, question)
    if not candidates:
        return []

    try:
        return _validated_candidates(
            candidates,
            identifiers,
            include_restricted,
            cfg,
        )
    except Exception:
        logger.exception("Follow-up validation failed")
        return []
