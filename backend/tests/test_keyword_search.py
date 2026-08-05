"""BM25 keyword retrieval: tokenizer, scoring, RRF fusion, cache, fallback."""

from __future__ import annotations

import pytest

from app.modules.retrieval import keyword_search
from app.modules.retrieval.keyword_search import (
    Bm25Index,
    Bm25IndexCache,
    bm25_search,
    rrf_merge,
    tokenize,
)


def _row(chunk_id: str, text: str, **extra) -> dict:
    return {"chunk_id": chunk_id, "document_id": "doc-1", "text": text, **extra}


# ── tokenizer ────────────────────────────────────────────────────────────────


def test_tokenize_latin_words_lowercased_without_stopwords() -> None:
    tokens = tokenize("The NIST Framework was published in 2023.")
    assert "nist" in tokens
    assert "framework" in tokens
    assert "2023" in tokens
    assert "the" not in tokens
    assert "was" not in tokens


def test_tokenize_keeps_accented_words_whole() -> None:
    assert "stratégie" in tokenize("La stratégie nationale")


def test_tokenize_cjk_produces_bigrams() -> None:
    tokens = tokenize("人工智能")
    assert tokens[:3] == ["人工", "工智", "智能"]


def test_tokenize_mixed_text_yields_both_streams() -> None:
    tokens = tokenize("EU AI Act 与人工智能法案")
    assert "eu" in tokens
    assert "act" in tokens
    assert "人工" in tokens
    assert "法案" in tokens


def test_tokenize_single_cjk_char_is_kept() -> None:
    assert "法" in tokenize("法")


# ── BM25 scoring ─────────────────────────────────────────────────────────────


def test_bm25_exact_term_beats_unrelated_chunk() -> None:
    index = Bm25Index(
        [
            _row("a", "Executive Order 14110 directs federal agencies on AI safety."),
            _row("b", "Weather patterns shifted across the Pacific this spring."),
            _row("c", "The order requires agencies to appoint chief AI officers."),
        ]
    )
    results = index.search("What does Executive Order 14110 require?", limit=3)
    assert results
    assert results[0][0]["chunk_id"] == "a"
    returned_ids = {row["chunk_id"] for row, _ in results}
    assert "b" not in returned_ids


def test_bm25_chinese_query_matches_chinese_chunk() -> None:
    index = Bm25Index(
        [
            _row("zh", "生成式人工智能服务管理暂行办法自2023年8月15日起施行。"),
            _row("en", "This chunk is about maritime shipping lanes."),
        ]
    )
    results = index.search("生成式人工智能管理办法什么时候施行？", limit=2)
    assert results
    assert results[0][0]["chunk_id"] == "zh"


def test_bm25_empty_query_and_empty_corpus_are_safe() -> None:
    assert Bm25Index([]).search("anything", limit=5) == []
    index = Bm25Index([_row("a", "some text")])
    assert index.search("", limit=5) == []


def test_bm25_scores_are_positive_and_ranked_descending() -> None:
    index = Bm25Index(
        [
            _row("a", "carbon tax carbon tax carbon tax"),
            _row("b", "carbon emissions and other topics entirely"),
        ]
    )
    results = index.search("carbon tax", limit=2)
    scores = [score for _, score in results]
    assert all(score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)


# ── RRF fusion ───────────────────────────────────────────────────────────────


def test_rrf_chunk_in_both_rankings_wins() -> None:
    dense = [
        {"chunk_id": "both", "distance": 0.2},
        {"chunk_id": "dense-only", "distance": 0.3},
    ]
    sparse = [
        {"chunk_id": "sparse-only", "bm25_score": 9.0},
        {"chunk_id": "both", "bm25_score": 5.0},
    ]
    fused = rrf_merge(dense, sparse, limit=3)
    assert fused[0]["chunk_id"] == "both"
    # The winning row keeps its dense fields and gains the BM25 score.
    assert fused[0]["distance"] == 0.2
    assert fused[0]["bm25_score"] == 5.0


def test_rrf_result_is_truncated_to_limit() -> None:
    dense = [{"chunk_id": f"d{i}", "distance": i / 10} for i in range(5)]
    sparse = [{"chunk_id": f"s{i}", "bm25_score": 5 - i} for i in range(5)]
    assert len(rrf_merge(dense, sparse, limit=4)) == 4


def test_rrf_keeps_sparse_only_rows() -> None:
    dense = [{"chunk_id": "d", "distance": 0.1}]
    sparse = [{"chunk_id": "s", "bm25_score": 3.0}]
    ids = {row["chunk_id"] for row in rrf_merge(dense, sparse, limit=5)}
    assert ids == {"d", "s"}


# ── cache ────────────────────────────────────────────────────────────────────


def test_cache_reuses_index_for_same_fingerprint() -> None:
    cache = Bm25IndexCache()
    builds: list[int] = []

    def build() -> Bm25Index:
        builds.append(1)
        return Bm25Index([_row("a", "text")])

    key = (("doc-1",), False)
    first = cache.get(key, (1, "t1"), build)
    second = cache.get(key, (1, "t1"), build)
    assert first is second
    assert len(builds) == 1


def test_cache_rebuilds_when_fingerprint_changes() -> None:
    cache = Bm25IndexCache()
    builds: list[int] = []

    def build() -> Bm25Index:
        builds.append(1)
        return Bm25Index([_row("a", "text")])

    key = (("doc-1",), False)
    cache.get(key, (1, "t1"), build)
    cache.get(key, (2, "t2"), build)
    assert len(builds) == 2


def test_cache_evicts_oldest_beyond_capacity() -> None:
    cache = Bm25IndexCache(max_entries=2)
    for index in range(3):
        cache.get((f"k{index}",), (1, "t"), lambda: Bm25Index([]))
    builds: list[int] = []
    cache.get(("k0",), (1, "t"), lambda: builds.append(1) or Bm25Index([]))
    assert builds  # k0 was evicted, so it had to rebuild


# ── bm25_search orchestration ────────────────────────────────────────────────


def test_bm25_search_returns_rows_with_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.documents.repositories import chunk_texts

    keyword_search._index_cache.clear()
    monkeypatch.setattr(
        chunk_texts.chunk_text_repository,
        "corpus_fingerprint",
        lambda document_ids=None, *, include_restricted=False: (2, "t1"),
    )
    monkeypatch.setattr(
        chunk_texts.chunk_text_repository,
        "list_chunk_rows",
        lambda document_ids=None, *, include_restricted=False: [
            _row("a", "Executive Order 14110 on artificial intelligence."),
            _row("b", "Unrelated horticulture content."),
        ],
    )
    results = bm25_search("Executive Order 14110", document_ids=["doc-1"], limit=5)
    assert results
    assert results[0]["chunk_id"] == "a"
    assert results[0]["bm25_score"] > 0


def test_bm25_search_swallows_repository_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.documents.repositories import chunk_texts

    keyword_search._index_cache.clear()

    def boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(chunk_texts.chunk_text_repository, "corpus_fingerprint", boom)
    assert bm25_search("anything", limit=5) == []


def test_bm25_search_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_BM25_ENABLED", "false")
    assert bm25_search("anything", limit=5) == []


# ── hybrid wiring in documents/service/retrieval.py ─────────────────────────


def test_hybrid_candidates_backfills_real_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.documents import service as documents_service

    monkeypatch.setattr(
        keyword_search,
        "bm25_search",
        lambda *_args, **_kwargs: [
            {"chunk_id": "s1", "text": "sparse hit", "bm25_score": 4.0}
        ],
    )
    monkeypatch.setattr(
        documents_service.embedding_repository,
        "distances_for_chunks",
        lambda _query_vector, _ids: {"s1": 0.42},
    )
    dense = [{"chunk_id": "d1", "text": "dense hit", "distance": 0.2}]
    fused = documents_service.retrieval._hybrid_candidates(
        "q", dense, query_vector="[0.1]", candidate_limit=10
    )
    by_id = {candidate["chunk_id"]: candidate for candidate in fused}
    assert by_id["s1"]["distance"] == 0.42
    assert by_id["d1"]["distance"] == 0.2


def test_hybrid_candidates_defaults_to_worst_distance_when_unembedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.documents import service as documents_service

    monkeypatch.setattr(
        keyword_search,
        "bm25_search",
        lambda *_args, **_kwargs: [
            {"chunk_id": "s1", "text": "sparse hit", "bm25_score": 4.0}
        ],
    )
    monkeypatch.setattr(
        documents_service.embedding_repository,
        "distances_for_chunks",
        lambda _query_vector, _ids: {},
    )
    dense = [{"chunk_id": "d1", "text": "dense hit", "distance": 0.2}]
    fused = documents_service.retrieval._hybrid_candidates(
        "q", dense, query_vector="[0.1]", candidate_limit=10
    )
    by_id = {candidate["chunk_id"]: candidate for candidate in fused}
    assert by_id["s1"]["distance"] == 1.0


def test_hybrid_candidates_keeps_dense_when_sparse_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.documents import service as documents_service

    monkeypatch.setattr(keyword_search, "bm25_search", lambda *_args, **_kwargs: [])
    dense = [{"chunk_id": "d1", "text": "dense hit", "distance": 0.2}]
    assert (
        documents_service.retrieval._hybrid_candidates(
            "q", dense, query_vector="[0.1]", candidate_limit=10
        )
        == dense
    )


def test_hybrid_candidates_preserves_page_fallback_when_dense_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.documents import service as documents_service

    def fail_bm25(*_args, **_kwargs):
        raise AssertionError("BM25 must not run when dense retrieval found nothing")

    monkeypatch.setattr(keyword_search, "bm25_search", fail_bm25)
    assert (
        documents_service.retrieval._hybrid_candidates(
            "q", [], query_vector="[0.1]", candidate_limit=10
        )
        == []
    )
