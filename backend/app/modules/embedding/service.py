"""Public embedding API — the ONLY module the rest of the app should import.

Everything else (providers, tokenizers, config storage) is an implementation
detail of this package. Callers do:

    from app.modules.embedding import service as embedding
    embedding.embed_query(text) / embedding.embed_documents(texts)
    embedding.count_tokens(text) / embedding.vector_literal(vec)
    embedding.active_dimension() / embedding.evidence_distance_threshold()

The active provider is built from the persisted EmbeddingConfig and cached;
saving new config rebuilds it, so switching models is a settings change, not a
code change. The fastembed model itself is cached by name, so rebuilding a
provider is cheap unless the model actually changed.
"""

from __future__ import annotations

from app.modules.embedding import providers, tokens
from app.modules.embedding.providers import (
    EmbeddingProvider,
    LocalFastembedProvider,
    OpenAICompatibleProvider,
)
from app.modules.embedding.repository import embedding_settings_repository
from app.modules.embedding.settings import EmbeddingConfig, mask_key, vector_table_name

# Lazy singleton cache of the active config + provider.
_cache: dict = {"config": None, "provider": None}


def _build_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "api":
        return OpenAICompatibleProvider(config)
    return LocalFastembedProvider(config)


def _reload() -> None:
    config = embedding_settings_repository.load()
    _cache["config"] = config
    _cache["provider"] = _build_provider(config)


def active_config() -> EmbeddingConfig:
    if _cache["config"] is None:
        _reload()
    return _cache["config"]


def _provider() -> EmbeddingProvider:
    if _cache["provider"] is None:
        _reload()
    return _cache["provider"]


# ── Embedding ────────────────────────────────────────────────────────────────
# to the outside

def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _provider().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return _provider().embed_query(text)


def count_tokens(text: str) -> int:
    return tokens.count_tokens(text, active_config(), _provider())


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in vector) + "]"


# ── Introspection used by retrieval / evidence / storage ─────────────────────


def active_dimension() -> int:
    return active_config().active_dimension()


def active_model_id() -> str:
    return active_config().active_model_id()


def evidence_distance_threshold() -> float:
    return active_config().evidence_distance_threshold


def active_vector_table() -> str:
    """Name of the vector table for the active model (one table per model)."""
    cfg = active_config()
    return vector_table_name(cfg.active_model_id(), cfg.active_dimension())


# ── Admin config management ──────────────────────────────────────────────────


def _resolve_dimension(config: EmbeddingConfig) -> int:
    """True vector dimension of a config, probing once when we can't know it.

    Needed because the vector table is created at a fixed dimension: an API model
    with auto-detect on (or an unknown local model) must be probed so the stored
    dimension matches what the model actually returns.
    """
    from app.modules.embedding.settings import KNOWN_LOCAL_DIMENSIONS

    if config.provider == "local":
        if config.local_model in KNOWN_LOCAL_DIMENSIONS:
            return KNOWN_LOCAL_DIMENSIONS[config.local_model]
        return providers.probe(config)["dimension"]
    if config.auto_detect_dimensions:
        return providers.probe(config)["dimension"]
    return config.dimensions


def update_config(partial: dict) -> EmbeddingConfig:
    """Merge a partial update over the current config, resolve its dimension, persist.

    A blank api_key means "keep the existing key" so the secret is never wiped by
    a form submit that left the field empty. Saving probes the model once to lock
    in the real dimension (raises if the model/API is unreachable — you can't save
    an unverified embedding target).
    """
    current = active_config().model_dump()
    merged = {**current, **{k: v for k, v in partial.items() if v is not None}}
    if not (partial.get("api_key") or "").strip():
        merged["api_key"] = current.get("api_key", "")
    config = EmbeddingConfig(**merged)
    resolved = _resolve_dimension(config)
    if resolved != config.dimensions:
        config = config.model_copy(update={"dimensions": resolved})
    embedding_settings_repository.save(config)
    _reload()
    return config


def test_connection(partial: dict) -> dict:
    """Probe connectivity for a candidate config (merged over the stored one)."""
    current = active_config().model_dump()
    merged = {**current, **{k: v for k, v in partial.items() if v is not None}}
    if not (partial.get("api_key") or "").strip():
        merged["api_key"] = current.get("api_key", "")
    return providers.probe(EmbeddingConfig(**merged))


def status() -> dict:
    """Config for the admin UI, with the API key masked (never sent raw)."""
    config = active_config()
    data = config.model_dump()
    data.pop("api_key", None)
    return {
        "settings": data,
        "status": {
            "provider": config.provider,
            "model": config.active_model_id(),
            "dimension": config.active_dimension(),
            "vector_table": active_vector_table(),
            "api_key_masked": mask_key(config.api_key),
        },
    }
