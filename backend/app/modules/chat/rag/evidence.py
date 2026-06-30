from __future__ import annotations

MIN_CONTEXT_CHARACTERS = 200
MIN_RETRIEVED_CHUNKS = 1
MAX_VECTOR_DISTANCE = 0.85

REASON_NO_TEXT = (
    "No extractable text was found in the selected documents."
)
REASON_LOW_RELEVANCE = (
    "Retrieved passages are not sufficiently similar to your question."
)
REASON_SHORT_CONTEXT = (
    "Too little relevant text was retrieved to support a reliable answer."
)


def assess_evidence_sufficiency(
    *,
    question: str,
    chunks: list[dict],
    pages: list[dict],
    context: str,
    used_vector_retrieval: bool,
) -> tuple[bool, str | None]:
    clean_context = context.strip()
    if len(clean_context) < MIN_CONTEXT_CHARACTERS:
        if pages and sum(len(page.get("text", "")) for page in pages) >= MIN_CONTEXT_CHARACTERS:
            return True, None
        return False, REASON_NO_TEXT

    if used_vector_retrieval:
        if len(chunks) < MIN_RETRIEVED_CHUNKS:
            return False, REASON_LOW_RELEVANCE

        best_distance = min(float(chunk.get("distance", 1.0)) for chunk in chunks)
        if best_distance > MAX_VECTOR_DISTANCE:
            return False, REASON_LOW_RELEVANCE

        return True, None

    # Page-level fallback when embeddings are not available yet.
    if len(clean_context) >= MIN_CONTEXT_CHARACTERS:
        return True, None

    return False, REASON_SHORT_CONTEXT
