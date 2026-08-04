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
from app.modules.embedding.settings import (
    DEFAULT_API_EVIDENCE_DISTANCE,
    DEFAULT_LOCAL_EVIDENCE_DISTANCE,
    EmbeddingConfig,
    vector_table_name,
)

# Lazy singleton cache of the active config + provider.
_cache: dict = {"config": None, "provider": None}


def _resolved_config(config: EmbeddingConfig) -> EmbeddingConfig:
    """Fill api_base_url + api_key from the catalog + central provider-key store.

    api_provider (a catalog provider id like "zhipu") -> base URL from the model
    catalog and the key from the central store (entered on the LLM & API keys
    page). Falls back to the config's own api_base_url/api_key when there is no
    catalog/central entry (manual/legacy).
    """
    if config.provider != "api" or not config.api_provider or config.api_provider == "__manual__":
        return config
    from app.modules.catalog import service as catalog
    from app.modules.settings.service import get_provider_api_key

    base = catalog.resolve_base_url(config.api_provider, config.api_model, "embedding")
    key = get_provider_api_key(config.api_provider)
    return config.model_copy(
        update={"api_base_url": base or config.api_base_url, "api_key": key or config.api_key}
    )


def _build_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "api":
        return OpenAICompatibleProvider(_resolved_config(config))
    return LocalFastembedProvider(config)


def _reload() -> None:
    config = embedding_settings_repository.load()
    _cache["config"] = config
    _cache["provider"] = _build_provider(config)


def invalidate_provider_cache() -> None:
    """Rebuild the provider on next use (notably after a central key change)."""
    _cache["provider"] = None


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


def embed_queries(texts: list[str]) -> list[list[float]]:
    """Batch query-mode embedding, preserving query/passage asymmetry."""
    if not texts:
        return []
    return _provider().embed_queries(texts)


def embed_query(text: str) -> list[float]:
    return embed_queries([text])[0]


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
    return active_config().resolved_evidence_distance_threshold()


def active_vector_table() -> str:
    """Name of the vector table for the active model (one table per model)."""
    cfg = active_config()
    return vector_table_name(cfg.active_model_id(), cfg.active_dimension())


def api_credentials() -> tuple[str, str]:
    """Resolved (base_url, api_key) for the active embedding config in API mode."""
    resolved = _resolved_config(active_config())
    return resolved.api_base_url, resolved.api_key


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
        return providers.probe(_resolved_config(config))["dimension"]
    if config.auto_detect_dimensions:
        return providers.probe(_resolved_config(config))["dimension"]
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
    if "evidence_distance_threshold" in partial:
        # Explicit null means "use the selected provider's calibrated default".
        merged["evidence_distance_threshold"] = partial["evidence_distance_threshold"]
    provider_changed = (
        "api_provider" in partial
        and partial.get("api_provider") != current.get("api_provider")
    )
    if not (partial.get("api_key") or "").strip() and not provider_changed:
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
    provider_changed = (
        "api_provider" in partial
        and partial.get("api_provider") != current.get("api_provider")
    )
    if not (partial.get("api_key") or "").strip() and not provider_changed:
        merged["api_key"] = current.get("api_key", "")
    return providers.probe(_resolved_config(EmbeddingConfig(**merged)))


def status() -> dict:
    """Config for the admin UI, with the API key masked (never sent raw)."""
    config = active_config()
    data = config.model_dump()
    data.pop("api_key", None)
    if config.api_provider != "__manual__":
        data.pop("api_base_url", None)  # resolved from the catalog
    resolved = _resolved_config(config)
    return {
        "settings": data,
        "defaults": {
            "local": {"evidence_distance_threshold": DEFAULT_LOCAL_EVIDENCE_DISTANCE},
            "api": {"evidence_distance_threshold": DEFAULT_API_EVIDENCE_DISTANCE},
        },
        "status": {
            "provider": config.provider,
            "api_provider": config.api_provider,
            "model": config.active_model_id(),
            "dimension": config.active_dimension(),
            "vector_table": active_vector_table(),
            "api_key_configured": bool(resolved.api_key),
            "evidence_distance_threshold": config.resolved_evidence_distance_threshold(),
        },
    }
