from __future__ import annotations

from app.modules.documents import service


def configure_retrieval_dependencies(monkeypatch) -> dict:
    captured: dict = {}

    monkeypatch.setattr(
        service.document_repository,
        "get_record",
        lambda identifier, include_restricted=False: {
            "id": identifier,
        },
    )
    monkeypatch.setattr(
        service.embedding,
        "embed_query",
        lambda question: [0.1] * 384,
    )
    monkeypatch.setattr(
        service.embedding,
        "vector_literal",
        lambda vector: "[query-vector]",
    )

    candidates = [
        {
            "chunk_id": f"chunk-{index}",
            "text": f"Candidate {index}",
            "distance": index / 100,
        }
        for index in range(24)
    ]

    def fake_retrieve(
        query_vector: str,
        document_ids: list[str],
        *,
        limit: int,
    ) -> list[dict]:
        captured["query_vector"] = query_vector
        captured["document_ids"] = document_ids
        captured["candidate_limit"] = limit
        return candidates[:limit]

    monkeypatch.setattr(
        service.embedding_repository,
        "retrieve",
        fake_retrieve,
    )

    captured["candidates"] = candidates
    return captured


def test_retrieve_relevant_chunks_uses_reranker(
    monkeypatch,
) -> None:
    captured = configure_retrieval_dependencies(monkeypatch)

    def fake_rerank(
        question: str,
        chunks: list[dict],
        *,
        limit: int,
    ) -> list[dict]:
        captured["rerank_question"] = question
        captured["rerank_chunk_count"] = len(chunks)
        captured["final_limit"] = limit
        return list(reversed(chunks))[:limit]

    monkeypatch.setattr(
        service,
        "rerank_chunks",
        fake_rerank,
    )

    results = service.retrieve_relevant_chunks(
        "Policy question",
        ["document-1"],
        limit=8,
    )

    assert captured["candidate_limit"] == 24
    assert captured["rerank_chunk_count"] == 24
    assert captured["final_limit"] == 8
    assert captured["rerank_question"] == "Policy question"
    assert results[0]["chunk_id"] == "chunk-23"


def test_retrieve_relevant_chunks_falls_back_when_reranker_fails(
    monkeypatch,
) -> None:
    captured = configure_retrieval_dependencies(monkeypatch)

    def failing_reranker(
        question: str,
        chunks: list[dict],
        *,
        limit: int,
    ) -> list[dict]:
        raise RuntimeError("Reranker unavailable")

    monkeypatch.setattr(
        service,
        "rerank_chunks",
        failing_reranker,
    )

    results = service.retrieve_relevant_chunks(
        "Policy question",
        ["document-1"],
        limit=8,
    )

    assert captured["candidate_limit"] == 24
    assert len(results) == 8
    assert results[0]["chunk_id"] == "chunk-0"
