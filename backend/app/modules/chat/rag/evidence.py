from __future__ import annotations

from app.modules.embedding import service as embedding

MIN_CONTEXT_CHARACTERS = 200

# Cosine distance threshold — chunks with distance above this are considered off-topic.
# Lower value = stricter (0 = identical, 1 = orthogonal, 2 = opposite).
# This constant is the fallback default; the live value is admin-tunable per
# embedding model via Manage > Embedding (read through max_vector_distance()).
MAX_VECTOR_DISTANCE = 0.45


def max_vector_distance() -> float:
    """Live cosine-distance cutoff (admin-configurable, falls back to the constant)."""
    try:
        return embedding.evidence_distance_threshold()
    except Exception:
        return MAX_VECTOR_DISTANCE

# Reranker score threshold — the bge-reranker-base cross-encoder returns scores
# roughly in the range [-10, 10]; values below this indicate no relevant passage found.
# Calibrated empirically: relevant passages score >= -5.9 on the US AI Action Plan corpus.
# Off-topic passages (climate, NHS, visa) score <= -7.2. Threshold -7.0 sits in the gap.
MIN_RERANKER_SCORE = -7.0

REASON_NO_TEXT = "No extractable text was found in the selected documents."
REASON_LOW_RELEVANCE = (
    "The selected documents do not contain passages closely related to your question."
)
REASON_SHORT_CONTEXT = "Too little relevant text was retrieved to support a reliable answer."


def assess_evidence_sufficiency(
    *,
    question: str,
    raw_chunks: list[dict],
    pages: list[dict],
    context: str,
    has_embeddings: bool,
) -> tuple[bool, str | None]:
    """Return (sufficient, reason).

    has_embeddings – True when the documents have been indexed and vector
    search returned at least one chunk (regardless of relevance score).
    raw_chunks – ALL chunks returned after reranking (before distance filter).
    """
    clean_context = context.strip()
    if len(clean_context) < MIN_CONTEXT_CHARACTERS:
        # Page-level bypass only applies to documents that were never indexed.
        # For indexed documents, short context means no relevant chunks were found —
        # falling through to the semantic gates is the correct behaviour.
        if (
            not has_embeddings
            and pages
            and sum(len(p.get("text", "")) for p in pages) >= MIN_CONTEXT_CHARACTERS
        ):
            return True, None
        return False, REASON_NO_TEXT

    if has_embeddings:
        if not raw_chunks:
            return False, REASON_LOW_RELEVANCE

        # Primary signal: cosine distance of the closest matching chunk.
        best_distance = min(float(c.get("distance", 1.0)) for c in raw_chunks)
        if best_distance > max_vector_distance():
            return False, REASON_LOW_RELEVANCE

        # Secondary signal: cross-encoder reranker score.
        # If even the best reranker score is very low the cross-encoder has
        # determined that no retrieved passage is actually relevant.
        reranker_scores = [c["reranker_score"] for c in raw_chunks if "reranker_score" in c]
        if reranker_scores:
            best_reranker = max(reranker_scores)
            if best_reranker < MIN_RERANKER_SCORE:
                return False, REASON_LOW_RELEVANCE

        return True, None

    # Page-level fallback (document not yet indexed with embeddings).
    if len(clean_context) >= MIN_CONTEXT_CHARACTERS:
        return True, None

    return False, REASON_SHORT_CONTEXT
