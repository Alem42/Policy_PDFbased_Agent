from __future__ import annotations

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"


@lru_cache(maxsize=1)
def _load_reranker() -> TextCrossEncoder:
    """Load and cache the cross-encoder reranker."""
    return TextCrossEncoder(model_name=RERANKER_MODEL_NAME)


def rerank_chunks(
    question: str,
    chunks: list[dict],
    *,
    limit: int,
) -> list[dict]:
    """Rerank retrieved chunks by cross-encoder relevance score."""
    if not question.strip():
        raise ValueError("Question must not be blank.")

    if limit <= 0:
        raise ValueError("Reranker limit must be greater than zero.")

    if not chunks:
        return []

    texts: list[str] = []

    for chunk in chunks:
        text = chunk.get("text")

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Every retrieved chunk must contain non-empty text.")

        texts.append(text)

    scores = [
        float(score)
        for score in _load_reranker().rerank(question, texts)
    ]

    if len(scores) != len(chunks):
        raise RuntimeError(
            "Reranker returned a different number of scores than chunks."
        )

    ranked_chunks = [
        {
            **chunk,
            "reranker_score": score,
        }
        for chunk, score in zip(chunks, scores, strict=True)
    ]

    ranked_chunks.sort(
        key=lambda chunk: chunk["reranker_score"],
        reverse=True,
    )

    return ranked_chunks[:limit]
