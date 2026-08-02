from __future__ import annotations

import re

from app.modules.embedding import service as embedding
from app.modules.reranking import service as reranking

MIN_CONTEXT_CHARACTERS = 200
MAX_VECTOR_DISTANCE = 0.45
MIN_RERANKER_SCORE = -7.0

REASON_NO_TEXT = "No extractable text was found in the selected documents."
REASON_LOW_RELEVANCE = (
    "The selected documents do not contain passages closely related to your question."
)
REASON_SHORT_CONTEXT = "Too little relevant text was retrieved to support a reliable answer."

_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "may",
    "of",
    "on",
    "one",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "which",
    "who",
}


def max_vector_distance() -> float:
    """Return the active embedding model's evidence cutoff."""

    try:
        return embedding.evidence_distance_threshold()
    except Exception:
        return MAX_VECTOR_DISTANCE


def min_reranker_score() -> float:
    """Return the active reranker provider's evidence floor."""

    try:
        return reranking.min_reranker_score()
    except Exception:
        return MIN_RERANKER_SCORE


def lexical_support(question: str, text: str) -> tuple[int, float]:
    """Return matched meaningful query terms and query-term coverage.

    This is a deterministic backstop for embedding providers whose cosine
    scales differ from the configured threshold. It is not used alone for weak
    matches; it must agree with the reranker or have very strong coverage.
    """

    query_terms = {word for word in _WORD.findall(question.lower()) if word not in _STOP_WORDS}
    if not query_terms:
        return 0, 0.0
    text_terms = set(_WORD.findall(text.lower()))
    matches = len(query_terms & text_terms)
    return matches, matches / len(query_terms)


def is_chunk_relevant(question: str, chunk: dict) -> bool:
    """Combine dense, reranker, and lexical signals conservatively."""

    distance_passes = float(chunk.get("distance", 1.0)) <= max_vector_distance()
    reranker_score = chunk.get("reranker_score")
    reranker_passes = (
        reranker_score is None or float(reranker_score) >= min_reranker_score()
    )
    if distance_passes:
        return reranker_passes

    matches, coverage = lexical_support(question, chunk.get("text", ""))
    lexical_passes = matches >= 2 and coverage >= 0.30
    if not lexical_passes:
        return False
    if reranker_score is not None:
        return reranker_passes
    return matches >= 3 and coverage >= 0.60


def assess_evidence_sufficiency(
    *,
    question: str,
    raw_chunks: list[dict],
    pages: list[dict],
    context: str,
    has_embeddings: bool,
) -> tuple[bool, str | None]:
    """Apply the deterministic evidence gate to retrieved content."""

    if has_embeddings:
        if not raw_chunks:
            return False, REASON_LOW_RELEVANCE
        if not any(is_chunk_relevant(question, chunk) for chunk in raw_chunks):
            return False, REASON_LOW_RELEVANCE
        if len(context.strip()) < MIN_CONTEXT_CHARACTERS:
            return False, REASON_SHORT_CONTEXT
        return True, None

    clean_context = context.strip()
    if len(clean_context) < MIN_CONTEXT_CHARACTERS:
        if pages and sum(len(page.get("text", "")) for page in pages) >= MIN_CONTEXT_CHARACTERS:
            return True, None
        return False, REASON_NO_TEXT
    if len(clean_context) >= MIN_CONTEXT_CHARACTERS:
        return True, None
    return False, REASON_SHORT_CONTEXT
