"""Embedding configuration model + defaults.

This package is the single home for all embedding logic. The rest of the app
only ever calls `embedding.service`; it never imports a concrete provider or
touches the model directly. That keeps swapping the embedding model (local <->
API, or one API for another) contained to this folder.

`EmbeddingConfig` mirrors the Manage > Embedding admin page one-to-one. It is
persisted as a single JSON row (see repository.py) so an admin can retune the
pipeline without a redeploy.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# The pre-existing table holds the default local model's vectors. Mapping that
# (model, dim) back to it preserves already-embedded data (no re-embed on
# upgrade). Every other model gets its own on-demand table so multiple models'
# vectors coexist and switching is instant (just read the other table).
LEGACY_VECTOR_TABLE = "chunk_embeddings"
_LEGACY_MODEL = ("BAAI/bge-small-en-v1.5", 384)


def vector_table_name(model_id: str, dim: int) -> str:
    """Deterministic vector-table name for a (model, dim). One table per model."""
    if (model_id, dim) == _LEGACY_MODEL:
        return LEGACY_VECTOR_TABLE
    slug = re.sub(r"[^a-z0-9]+", "_", model_id.lower()).strip("_")
    return f"chunk_vectors_{slug}_{dim}"[:63]  # Postgres identifier limit

# Local fastembed models we expose in the UI, mapped to their output dimension.
# fastembed downloads weights + tokenizer on first use; dimension comes with it.
# NOTE: listing a model here does NOT mean it is downloaded — only the active one
# is fetched. The bundled cache currently holds bge-small (embedding) + the reranker.
KNOWN_LOCAL_DIMENSIONS: dict[str, int] = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "intfloat/multilingual-e5-large": 1024,
}

DEFAULT_LOCAL_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_LOCAL_EVIDENCE_DISTANCE = 0.45
DEFAULT_API_EVIDENCE_DISTANCE = 0.50


def default_evidence_distance(provider: str) -> float:
    """Return the demo-calibrated evidence cutoff for a provider mode."""

    return (
        DEFAULT_API_EVIDENCE_DISTANCE
        if provider == "api"
        else DEFAULT_LOCAL_EVIDENCE_DISTANCE
    )


class EmbeddingConfig(BaseModel):
    """Admin-tunable embedding settings (one row, persisted as JSON)."""

    provider: Literal["local", "api"] = "local"

    # Local (fastembed) provider.
    local_model: str = DEFAULT_LOCAL_MODEL

    # API provider. `api_provider` is a catalog provider id (e.g. "zhipu"); the
    # base URL is resolved from the catalog and the key from the central provider
    # key store (LLM & API keys page) — NOT stored here. api_base_url/api_key
    # remain only as a manual/legacy fallback when there is no catalog entry.
    api_provider: str = ""
    api_base_url: str = ""
    api_key: str = ""  # never returned raw to the client — masked in the API layer
    api_model: str = ""
    dimensions: int = Field(default=384, ge=1)
    auto_detect_dimensions: bool = True
    symmetric: bool = True  # API models are usually symmetric (query == passage encoding)

    # Chunking / token accounting.
    batch_size: int = Field(default=32, ge=1, le=256)
    chunk_token_budget: int = Field(default=480, ge=64)
    token_counting: Literal["auto", "model", "tiktoken"] = "auto"

    # Retrieval / evidence knobs (calibrated per embedding model).
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"
    evidence_distance_threshold: float | None = Field(default=None, ge=0.10, le=1.00)
    # (reranker settings moved to the reranking package / Manage > Reranker)

    def active_model_id(self) -> str:
        """Human identifier of the model currently in use."""
        return self.local_model if self.provider == "local" else (self.api_model or "unknown")

    def active_dimension(self) -> int:
        """Vector length the active model produces."""
        if self.provider == "local":
            return KNOWN_LOCAL_DIMENSIONS.get(self.local_model, self.dimensions)
        return self.dimensions

    def resolved_evidence_distance_threshold(self) -> float:
        if self.evidence_distance_threshold is not None:
            return self.evidence_distance_threshold
        return default_evidence_distance(self.provider)


def mask_key(key: str | None) -> str | None:
    """Return a display-safe hint of a secret key, never the raw value."""
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"
