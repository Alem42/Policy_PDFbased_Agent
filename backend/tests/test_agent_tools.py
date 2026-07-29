"""Pure-logic pieces of the web-search agent: evidence gating, citation
dedup, and admin-only tool filtering. These don't hit the database."""

from __future__ import annotations

import pytest

from app.modules.chat.rag.agent.graph import ALL_TOOLS, NON_ADMIN_TOOLS
from app.modules.chat.rag.agent.state import add_citations
from app.modules.chat.rag.agent.tools import _cosine_distance, _score_web_results
from app.modules.chat.rag.web_search.contracts import WebSearchResult


def test_cosine_distance_identical_vectors_is_zero() -> None:
    assert _cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_vectors_is_one() -> None:
    assert _cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_distance_zero_vector_is_max_distance() -> None:
    assert _cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0


def test_score_web_results_empty_is_insufficient() -> None:
    sufficient, reason, candidates = _score_web_results("query", [])
    assert sufficient is False
    assert candidates == []
    assert reason


def test_score_web_results_close_result_passes_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Same vector for query and the one result -> distance 0, well under threshold.
    monkeypatch.setattr(tools_module, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(tools_module, "embed_documents", lambda texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(tools_module, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module, "reranker_enabled", lambda: False)

    results = [WebSearchResult(url="https://example.com", title="Example", content="relevant text")]
    sufficient, reason, candidates = _score_web_results("query", results)

    assert sufficient is True
    assert reason is None
    assert candidates[0]["passed"] is True


def test_score_web_results_far_result_fails_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Orthogonal vectors -> distance 1.0, well over any sane threshold.
    monkeypatch.setattr(tools_module, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(tools_module, "embed_documents", lambda texts: [[0.0, 1.0] for _ in texts])
    monkeypatch.setattr(tools_module, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module, "reranker_enabled", lambda: False)

    results = [
        WebSearchResult(url="https://example.com", title="Example", content="unrelated text")
    ]
    sufficient, reason, candidates = _score_web_results("query", results)

    assert sufficient is False
    assert candidates[0]["passed"] is False


def test_add_citations_deduplicates_by_identity() -> None:
    first = [{"document_id": "d1", "chunk_id": "c1", "title": "A"}]
    duplicate_and_new = [
        {"document_id": "d1", "chunk_id": "c1", "title": "A"},  # same identity, dropped
        {"document_id": "d2", "chunk_id": "c2", "title": "B"},
    ]
    merged = add_citations(first, duplicate_and_new)
    assert len(merged) == 2
    assert [c["chunk_id"] for c in merged] == ["c1", "c2"]


def test_add_citations_treats_distinct_web_urls_as_distinct() -> None:
    first = [{"source_url": "https://a.example.com", "title": "A"}]
    second = [{"source_url": "https://b.example.com", "title": "B"}]
    merged = add_citations(first, second)
    assert len(merged) == 2


def test_import_web_page_hidden_from_non_admin_tool_binding() -> None:
    non_admin_names = {t.name for t in NON_ADMIN_TOOLS}
    all_names = {t.name for t in ALL_TOOLS}
    assert "import_web_page" not in non_admin_names
    assert "import_web_page" in all_names
    # Every other tool remains available to non-admin sessions.
    assert all_names - non_admin_names == {"import_web_page"}
