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

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.chat.rag.evidence import max_vector_distance, min_reranker_score
from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.config import SuggestionConfig
from app.modules.chat.suggestions.profile import personalization_hint
from app.modules.documents.service import retrieve_relevant_chunks

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
    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


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
    client = create_chat_client(provider, selected_model, temperature=cfg.temperature)
    response = client.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return _parse_candidates(str(response.content))


def _passes_evidence_gate(
    candidate: str,
    identifiers: list[str],
    include_restricted: bool,
    cfg: SuggestionConfig,
    gate_distance: float,
) -> bool:
    """Approach D: keep only candidates the corpus can actually answer.

    Reuses retrieve_relevant_chunks (identifier resolution, multi-file pgvector
    filter, and the reranker toggle) so validation mirrors a real question exactly.
    """
    chunks = retrieve_relevant_chunks(
        candidate,
        identifiers,
        limit=cfg.validation_top_k,
        include_restricted=include_restricted,
    )
    if not chunks:
        return False
    best_distance = min(float(c.get("distance", 1.0)) for c in chunks)
    if best_distance > gate_distance:
        return False
    if cfg.use_reranker_validation:
        scores = [c["reranker_score"] for c in chunks if "reranker_score" in c]
        if scores and max(scores) < min_reranker_score():
            return False
    return True


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

    gate_distance = cfg.effective_distance(max_vector_distance())
    kept: list[str] = []
    for candidate in candidates:
        try:
            if _passes_evidence_gate(candidate, identifiers, include_restricted, cfg, gate_distance):
                kept.append(candidate)
        except Exception:
            logger.exception("Validation failed for candidate; dropping it")
        if len(kept) >= cfg.max_suggestions:
            break
    return kept
