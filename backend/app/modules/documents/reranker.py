from __future__ import annotations

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.core.config import get_settings, resolve_backend_path

RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"


@lru_cache(maxsize=2)
def _load_reranker(model_name: str = RERANKER_MODEL_NAME) -> TextCrossEncoder:
    """Load and cache the cross-encoder reranker (per model name, so the
    admin-configured local model actually takes effect on change)."""
    cache_dir = resolve_backend_path(get_settings().model_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextCrossEncoder(model_name=model_name, cache_dir=str(cache_dir))


def rerank_chunks(
    question: str,
    chunks: list[dict],
    *,
    limit: int,
    model_name: str | None = None,
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

    reranker = _load_reranker(model_name or RERANKER_MODEL_NAME)
    scores = [float(score) for score in reranker.rerank(question, texts)]

    if len(scores) != len(chunks):
        raise RuntimeError("Reranker returned a different number of scores than chunks.")

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
