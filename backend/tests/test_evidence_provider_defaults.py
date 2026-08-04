import pytest
from pydantic import ValidationError

from app.modules.embedding.settings import EmbeddingConfig
from app.modules.reranking import service as reranking_service
from app.modules.reranking.config import RerankingConfig


def test_embedding_evidence_default_is_provider_aware() -> None:
    assert EmbeddingConfig(provider="local").resolved_evidence_distance_threshold() == 0.45
    assert EmbeddingConfig(provider="api").resolved_evidence_distance_threshold() == 0.50


@pytest.mark.parametrize("value", [0.09, 1.01])
def test_embedding_rejects_unsafe_evidence_threshold(value: float) -> None:
    with pytest.raises(ValidationError):
        EmbeddingConfig(evidence_distance_threshold=value)


@pytest.mark.parametrize(
    "override",
    [
        {"dimensions": 63},
        {"dimensions": 4097},
        {"batch_size": 0},
        {"batch_size": 257},
        {"chunk_token_budget": 63},
        {"chunk_token_budget": 8193},
    ],
)
def test_embedding_rejects_unsafe_numeric_settings(override: dict) -> None:
    with pytest.raises(ValidationError):
        EmbeddingConfig(**override)


def test_reranker_evidence_default_is_provider_aware() -> None:
    assert RerankingConfig(provider="local").resolved_min_score() == -2.0
    assert RerankingConfig(provider="api").resolved_min_score() == 0.99


@pytest.mark.parametrize(
    ("provider", "value"),
    [("api", -0.01), ("api", 1.01), ("local", -10.01), ("local", 10.01)],
)
def test_reranker_rejects_score_from_wrong_scale(provider: str, value: float) -> None:
    with pytest.raises(ValidationError):
        RerankingConfig(provider=provider, min_score=value)


def test_reranker_explicit_null_restores_api_default(monkeypatch) -> None:
    monkeypatch.setattr(
        reranking_service,
        "active_config",
        lambda: RerankingConfig(provider="local", min_score=-4.0),
    )

    merged = reranking_service._merge({"provider": "api", "min_score": None})

    assert merged.min_score is None
    assert merged.resolved_min_score() == 0.99
