from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.documents import embeddings


class FakeEmbeddingModel:
    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.passage_batches: list[list[str]] = []
        self.query_inputs: list[str] = []

    def passage_embed(self, texts: list[str]):
        batch = list(texts)
        self.passage_batches.append(batch)
        for index, _ in enumerate(batch, start=1):
            yield [float(index)] * self.dimensions

    def query_embed(self, text: str):
        self.query_inputs.append(text)
        yield [0.5] * self.dimensions


def _settings(batch_size: int = 32) -> SimpleNamespace:
    return SimpleNamespace(
        embedding_model_name="test-model",
        embedding_batch_size=batch_size,
        default_embedding_dimensions=384,
    )


def test_embed_documents_batches_and_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeEmbeddingModel()
    monkeypatch.setattr(embeddings, "get_settings", lambda: _settings(batch_size=2))
    monkeypatch.setattr(embeddings, "_load_model", lambda _: model)

    vectors = embeddings.embed_documents(["one", "two", "three"])

    assert model.passage_batches == [["one", "two"], ["three"]]
    assert len(vectors) == 3
    assert all(len(vector) == 384 for vector in vectors)


def test_embed_query_uses_query_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeEmbeddingModel()
    monkeypatch.setattr(embeddings, "get_settings", lambda: _settings())
    monkeypatch.setattr(embeddings, "_load_model", lambda _: model)

    vector = embeddings.embed_query("What policy applies?")

    assert model.query_inputs == ["What policy applies?"]
    assert len(vector) == 384


def test_embedding_dimension_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FakeEmbeddingModel(dimensions=8)
    monkeypatch.setattr(embeddings, "get_settings", lambda: _settings())
    monkeypatch.setattr(embeddings, "_load_model", lambda _: model)

    with pytest.raises(ValueError, match="dimension mismatch"):
        embeddings.embed_documents(["policy text"])


def test_blank_text_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "get_settings", lambda: _settings())

    with pytest.raises(ValueError, match="must not be blank"):
        embeddings.embed_query("   ")

    with pytest.raises(ValueError, match="must not be blank"):
        embeddings.embed_documents(["valid", "  "])
