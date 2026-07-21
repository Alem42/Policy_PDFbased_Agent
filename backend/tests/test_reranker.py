from __future__ import annotations

import pytest

from app.modules.documents import reranker


class FakeReranker:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.received_question: str | None = None
        self.received_texts: list[str] | None = None

    def rerank(
        self,
        question: str,
        texts: list[str],
    ) -> list[float]:
        self.received_question = question
        self.received_texts = texts
        return self.scores


def test_rerank_chunks_orders_by_cross_encoder_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model = FakeReranker([0.2, 3.5, -1.0])

    monkeypatch.setattr(
        reranker,
        "_load_reranker",
        lambda: fake_model,
    )

    chunks = [
        {"chunk_id": "chunk-1", "text": "First candidate"},
        {"chunk_id": "chunk-2", "text": "Best candidate"},
        {"chunk_id": "chunk-3", "text": "Third candidate"},
    ]

    results = reranker.rerank_chunks(
        "Which candidate is most relevant?",
        chunks,
        limit=2,
    )

    assert [result["chunk_id"] for result in results] == [
        "chunk-2",
        "chunk-1",
    ]
    assert results[0]["reranker_score"] == 3.5
    assert fake_model.received_question == ("Which candidate is most relevant?")
    assert fake_model.received_texts == [
        "First candidate",
        "Best candidate",
        "Third candidate",
    ]


def test_rerank_chunks_returns_empty_without_loading_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_loaded() -> None:
        raise AssertionError("The reranker should not be loaded.")

    monkeypatch.setattr(
        reranker,
        "_load_reranker",
        fail_if_loaded,
    )

    assert (
        reranker.rerank_chunks(
            "A valid question",
            [],
            limit=5,
        )
        == []
    )


def test_rerank_chunks_rejects_blank_question() -> None:
    with pytest.raises(
        ValueError,
        match="Question must not be blank",
    ):
        reranker.rerank_chunks(
            "   ",
            [{"text": "Candidate"}],
            limit=1,
        )


def test_rerank_chunks_rejects_missing_text() -> None:
    with pytest.raises(
        ValueError,
        match="non-empty text",
    ):
        reranker.rerank_chunks(
            "Question",
            [{"chunk_id": "chunk-1"}],
            limit=1,
        )


def test_rerank_chunks_rejects_score_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reranker,
        "_load_reranker",
        lambda: FakeReranker([1.0]),
    )

    with pytest.raises(
        RuntimeError,
        match="different number of scores",
    ):
        reranker.rerank_chunks(
            "Question",
            [
                {"text": "First"},
                {"text": "Second"},
            ],
            limit=2,
        )
