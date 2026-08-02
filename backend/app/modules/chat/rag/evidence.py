"""Compatibility exports for the canonical retrieval evidence policy."""

from app.modules.retrieval.evidence import (
    MAX_VECTOR_DISTANCE,
    MIN_CONTEXT_CHARACTERS,
    MIN_RERANKER_SCORE,
    REASON_LOW_RELEVANCE,
    REASON_NO_TEXT,
    REASON_SHORT_CONTEXT,
    assess_evidence_sufficiency,
    max_vector_distance,
    min_reranker_score,
)

__all__ = [
    "MAX_VECTOR_DISTANCE",
    "MIN_CONTEXT_CHARACTERS",
    "MIN_RERANKER_SCORE",
    "REASON_LOW_RELEVANCE",
    "REASON_NO_TEXT",
    "REASON_SHORT_CONTEXT",
    "assess_evidence_sufficiency",
    "max_vector_distance",
    "min_reranker_score",
]
