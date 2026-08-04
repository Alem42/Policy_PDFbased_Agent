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

from pydantic import BaseModel, model_validator

DEFAULT_LOCAL_RERANKER = "BAAI/bge-reranker-base"
DEFAULT_LOCAL_MIN_SCORE = -2.0
DEFAULT_API_MIN_SCORE = 0.99


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

    @model_validator(mode="after")
    def validate_provider_score_scale(self) -> RerankingConfig:
        if self.min_score is None:
            return self
        if self.provider == "api" and not 0.0 <= self.min_score <= 1.0:
            raise ValueError("API reranker minimum score must be between 0 and 1.")
        if self.provider == "local" and not -10.0 <= self.min_score <= 10.0:
            raise ValueError("Local reranker minimum score must be between -10 and 10.")
        return self

    def active_model_id(self) -> str:
        return self.local_model if self.provider == "local" else (self.api_model or "rerank")

    def resolved_min_score(self) -> float:
        if self.min_score is not None:
            return self.min_score
        return DEFAULT_API_MIN_SCORE if self.provider == "api" else DEFAULT_LOCAL_MIN_SCORE
