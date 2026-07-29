"""Public reranking API — the only module the app should import for reranking.

    from app.modules.reranking import service as reranking
    reranking.enabled() / reranking.rerank(q, chunks, limit=n)
    reranking.min_reranker_score()   # evidence floor, provider-aware

Dispatches between the local cross-encoder (documents/reranker.py) and a
Cohere-style /rerank API. Blank API creds reuse the embedding provider's, so the
whole pipeline can sit on one provider (e.g. Zhipu).
"""

from __future__ import annotations

import logging

from app.core.settings_store import mask_secret
from app.modules.reranking import providers
from app.modules.reranking.config import RerankingConfig
from app.modules.reranking.repository import reranking_settings_repository

logger = logging.getLogger(__name__)

_cache: dict = {"config": None}


def _reload() -> None:
    _cache["config"] = reranking_settings_repository.load()


def active_config() -> RerankingConfig:
    if _cache["config"] is None:
        _reload()
    return _cache["config"]


def enabled() -> bool:
    return active_config().enabled


def min_reranker_score() -> float:
    """Evidence floor for the reranker score (provider-aware)."""
    return active_config().resolved_min_score()


def _resolve_creds(config: RerankingConfig) -> tuple[str, str, str]:
    """Reranker API base/key/model — reuse the embedding API creds when blank."""
    base, key = config.api_base_url, config.api_key
    if not base or not key:
        from app.modules.embedding import service as embedding

        emb = embedding.active_config()
        base = base or emb.api_base_url
        key = key or emb.api_key
    return base, key, config.api_model


def rerank(question: str, chunks: list[dict], *, limit: int) -> list[dict]:
    """Re-score candidates and return the top `limit`.

    May raise (the caller falls back to dense ranking), matching the old
    documents.reranker.rerank_chunks contract.
    """
    config = active_config()
    if config.provider == "local":
        from app.modules.documents.reranker import rerank_chunks as local_rerank

        return local_rerank(question, chunks, limit=limit)

    if not chunks:
        return []
    base_url, api_key, model = _resolve_creds(config)
    scores = providers.rerank_api(
        question,
        [chunk["text"] for chunk in chunks],
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    ranked = sorted(
        ({**chunk, "reranker_score": score} for chunk, score in zip(chunks, scores, strict=True)),
        key=lambda chunk: chunk["reranker_score"],
        reverse=True,
    )
    return ranked[:limit]


# ── Admin config management ──────────────────────────────────────────────────


def _merge(partial: dict) -> RerankingConfig:
    current = active_config().model_dump()
    merged = {**current, **{k: v for k, v in partial.items() if v is not None}}
    if not (partial.get("api_key") or "").strip():
        merged["api_key"] = current.get("api_key", "")
    return RerankingConfig(**merged)


def update_config(partial: dict) -> RerankingConfig:
    config = _merge(partial)
    reranking_settings_repository.save(config)
    _reload()
    return config


def test_connection(partial: dict) -> dict:
    config = _merge(partial)
    if config.provider == "local":
        from app.modules.documents.reranker import rerank_chunks as local_rerank

        out = local_rerank(
            "What is the capital of France?",
            [{"text": "Paris is the capital of France."}, {"text": "Bananas are a fruit."}],
            limit=2,
        )
        return {
            "model": config.local_model,
            "sample_scores": [round(c["reranker_score"], 4) for c in out],
        }
    base_url, api_key, model = _resolve_creds(config)
    return providers.probe_api(base_url, api_key, model)


def status() -> dict:
    """Config for the admin UI, API key masked."""
    config = active_config()
    data = config.model_dump()
    data.pop("api_key", None)
    _, resolved_key, _ = _resolve_creds(config)
    return {
        "settings": data,
        "status": {
            "enabled": config.enabled,
            "provider": config.provider,
            "model": config.active_model_id(),
            "min_score": config.resolved_min_score(),
            "api_key_masked": mask_secret(config.api_key),
            "reuses_embedding_key": (not config.api_key) and bool(resolved_key),
        },
    }
