"""Reranking configuration model + defaults.

The reranker is a cross-encoder that re-scores retrieved chunks against the
question -- a SEPARATE model from the embedding model. It can run locally
(fastembed bge-reranker, scores are logits ~[-10, 10]) or via a Cohere-style
/rerank API (e.g. Zhipu model "rerank", scores are relevance in [0, 1]).

Blank api_base_url/api_key reuse the embedding API credentials, so keeping the
whole pipeline on one provider (Zhipu embeddings + Zhipu rerank) is just
provider="api" with the model name.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DEFAULT_LOCAL_RERANKER = "BAAI/bge-reranker-base"


class RerankingConfig(BaseModel):
    """Admin-tunable reranking settings (one JSON row)."""

    enabled: bool = True
    provider: Literal["local", "api"] = "local"
    local_model: str = DEFAULT_LOCAL_RERANKER
    # api_provider = catalog provider id (e.g. "zhipu"); base URL from the catalog,
    # key from the central provider-key store. api_base_url/api_key are manual/legacy
    # fallbacks only. Blank api_provider + blank creds -> reuse the embedding creds.
    api_provider: str = ""
    api_base_url: str = ""
    api_key: str = ""
    api_model: str = "rerank"
    # Evidence floor for the reranker score. None -> provider default. Score
    # scales differ (local logits vs API [0,1]) so this must be recalibrated.
    min_score: float | None = None

    def active_model_id(self) -> str:
        return self.local_model if self.provider == "local" else (self.api_model or "rerank")

    def resolved_min_score(self) -> float:
        if self.min_score is not None:
            return self.min_score
        return 0.2 if self.provider == "api" else -7.0
