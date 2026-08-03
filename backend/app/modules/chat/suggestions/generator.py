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

from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.config import SuggestionConfig
from app.modules.chat.suggestions.profile import personalization_hint
from app.modules.retrieval.contracts import QuestionValidationRequest
from app.modules.retrieval.service import retrieval_service

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
        return retrieval_service.validate_questions(
            QuestionValidationRequest(
                questions=tuple(candidates),
                identifiers=tuple(identifiers),
                top_k=cfg.validation_top_k,
                max_results=cfg.max_suggestions,
                include_restricted=include_restricted,
                max_distance=cfg.validation_distance,
                use_reranker=cfg.use_reranker_validation,
            )
        )
    except Exception:
        logger.exception("Follow-up validation failed")
        return []
