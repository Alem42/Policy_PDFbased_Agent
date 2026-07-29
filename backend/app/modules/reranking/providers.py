"""API reranker provider (Cohere-style /rerank endpoint).

Covers Zhipu ("rerank"), Cohere, Jina, Voyage, SiliconFlow — they share the
shape: POST {model, query, documents[]} -> {results: [{index, relevance_score}]}.
The local (fastembed) reranker lives in documents/reranker.py; the service layer
dispatches between them.
"""

from __future__ import annotations

import time

import httpx


def _rerank_url(base_url: str) -> str:
    """Normalise any base to the single /rerank endpoint.

    Accepts '.../v4', '.../v4/', '.../v4/rerank', or an embedding base
    ('.../v4/embeddings') and always returns '.../v4/rerank'.
    """
    base = base_url.rstrip("/")
    for suffix in ("/rerank", "/embeddings"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/rerank"


def rerank_api(
    query: str,
    documents: list[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> list[float]:
    """Return a relevance score per document, aligned to the INPUT order."""
    if not base_url or not api_key or not model:
        raise ValueError("API reranker is missing base_url, api_key, or model.")
    response = httpx.post(
        _rerank_url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "query": query, "documents": documents},
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()["results"]
    scores = [0.0] * len(documents)
    for item in results:
        index = int(item.get("index", 0))
        if 0 <= index < len(scores):
            scores[index] = float(item.get("relevance_score", item.get("score", 0.0)))
    return scores


def probe_api(base_url: str, api_key: str, model: str) -> dict:
    """Rerank a relevant/irrelevant pair to verify connectivity + score scale."""
    started = time.perf_counter()
    scores = rerank_api(
        "What is the capital of France?",
        ["Paris is the capital of France.", "Bananas are a yellow fruit."],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    return {
        "model": model,
        "sample_scores": [round(s, 4) for s in scores],
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
