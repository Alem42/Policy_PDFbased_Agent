from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.chat import router as chat_router
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.suggestions import generator
from app.modules.chat.suggestions.config import SuggestionConfig
from app.modules.embedding import providers as embedding_providers
from app.modules.embedding import service as embedding_service


def _cfg(**over) -> SuggestionConfig:
    base = dict(
        enabled=True,
        max_suggestions=2,
        candidate_pool=5,
        use_reranker_validation=True,
        validation_top_k=5,
        validation_distance=None,
        temperature=0.0,
        max_question_chars=140,
        personalize=False,
    )
    base.update(over)
    return SuggestionConfig(**base)


def _patch_pipeline(monkeypatch, candidates, distances, reranker=5.0):
    """Stub one batched embedding/retrieval run with optional reranker scores."""
    captured: dict = {
        "resolve_calls": 0,
        "embed_calls": 0,
        "retrieve_calls": 0,
        "rerank_questions": [],
    }
    monkeypatch.setattr(generator, "_propose_candidates", lambda **kw: list(candidates))
    monkeypatch.setattr(generator, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(generator, "min_reranker_score", lambda: -7.0)

    def fake_resolve(identifiers, include_restricted=False):
        captured["resolve_calls"] += 1
        captured["last_identifiers"] = list(identifiers)
        captured["include_restricted"] = include_restricted
        return [f"resolved-{identifier}" for identifier in identifiers]

    def fake_embed_queries(texts):
        captured["embed_calls"] += 1
        captured["embedded_questions"] = list(texts)
        return [[float(index), 0.1] for index, _ in enumerate(texts)]

    def fake_retrieve_many(vectors, document_ids, *, limit):
        captured["retrieve_calls"] += 1
        captured["vectors"] = list(vectors)
        captured["document_ids"] = list(document_ids)
        captured["dense_limit"] = limit
        return [
            [{"distance": distances.get(candidate, 1.0), "text": f"Evidence for {candidate}"}]
            for candidate in candidates
        ]

    def fake_rerank(question, chunks, *, limit):
        captured["rerank_questions"].append(question)
        captured.setdefault("rerank_chunk_counts", []).append(len(chunks))
        return [{**chunk, "reranker_score": reranker} for chunk in chunks[:limit]]

    monkeypatch.setattr(generator, "resolve_document_ids", fake_resolve)
    monkeypatch.setattr(generator.embedding, "embed_queries", fake_embed_queries)
    monkeypatch.setattr(generator.embedding, "vector_literal", lambda vector: str(vector))
    monkeypatch.setattr(generator.embedding_repository, "retrieve_many", fake_retrieve_many)
    monkeypatch.setattr(generator.reranking, "enabled", lambda: True)
    monkeypatch.setattr(
        generator.reranking,
        "active_config",
        lambda: SimpleNamespace(provider="local"),
    )
    monkeypatch.setattr(generator.reranking, "rerank", fake_rerank)
    return captured


def test_only_answerable_candidates_survive_with_one_batch(monkeypatch):
    candidates = ["Q good1", "Q bad1", "Q good2", "Q bad2", "Q good3"]
    distances = {"Q good1": 0.2, "Q good2": 0.3, "Q good3": 0.25}
    captured = _patch_pipeline(monkeypatch, candidates, distances)

    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="some context",
        identifiers=["d1"],
        config=_cfg(max_suggestions=2),
    )

    assert out == ["Q good1", "Q good2"]
    assert captured["resolve_calls"] == 1
    assert captured["embed_calls"] == 1
    assert captured["retrieve_calls"] == 1
    assert captured["rerank_questions"] == ["Q good1", "Q good2"]


def test_disabled_returns_empty(monkeypatch):
    captured = _patch_pipeline(monkeypatch, ["Q good1"], {"Q good1": 0.1})
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(enabled=False),
    )
    assert out == []
    assert captured["embed_calls"] == 0


def test_llm_error_returns_empty(monkeypatch):
    def boom(**kw):
        raise RuntimeError("llm down")

    monkeypatch.setattr(generator, "_propose_candidates", boom)
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(),
    )
    assert out == []


def test_reranker_floor_rejects_off_topic(monkeypatch):
    _patch_pipeline(monkeypatch, ["Q1"], {"Q1": 0.2}, reranker=-9.0)
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(),
    )
    assert out == []


def test_distance_rejection_happens_before_reranker(monkeypatch):
    captured = _patch_pipeline(monkeypatch, ["Q bad"], {"Q bad": 0.9})
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(),
    )
    assert out == []
    assert captured["rerank_questions"] == []


def test_dedupes_original_and_history(monkeypatch):
    candidates = ["What are the pillars?", "Already asked before"]
    captured = _patch_pipeline(
        monkeypatch,
        candidates,
        {"What are the pillars?": 0.1, "Already asked before": 0.1},
    )
    out = generator.generate_followup_suggestions(
        question="What are the pillars?",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        history=[{"role": "user", "content": "Already asked before"}],
        config=_cfg(max_suggestions=3),
    )
    assert out == []
    assert captured["embed_calls"] == 0


def test_multifile_resolves_all_identifiers_once(monkeypatch):
    identifiers = [f"doc-{index}" for index in range(12)]
    captured = _patch_pipeline(monkeypatch, ["Q1"], {"Q1": 0.1})
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=identifiers,
        include_restricted=True,
        config=_cfg(max_suggestions=1),
    )
    assert out == ["Q1"]
    assert captured["resolve_calls"] == 1
    assert captured["last_identifiers"] == identifiers
    assert captured["document_ids"] == [f"resolved-{identifier}" for identifier in identifiers]
    assert captured["include_restricted"] is True


def test_validation_distance_override_is_stricter(monkeypatch):
    captured = _patch_pipeline(monkeypatch, ["Q1"], {"Q1": 0.4})
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(validation_distance=0.3),
    )
    assert out == []
    assert captured["rerank_questions"] == []


def test_reranker_only_receives_validation_top_k(monkeypatch):
    candidates = ["Q1"]
    captured = _patch_pipeline(monkeypatch, candidates, {"Q1": 0.1})

    def twenty_chunks(vectors, document_ids, *, limit):
        captured["dense_limit"] = limit
        return [[{"distance": 0.1 + index / 1000, "text": str(index)} for index in range(20)]]

    monkeypatch.setattr(generator.embedding_repository, "retrieve_many", twenty_chunks)
    out = generator.generate_followup_suggestions(
        question="original",
        answer="ans",
        context="ctx",
        identifiers=["d1"],
        config=_cfg(validation_top_k=4),
    )
    assert out == ["Q1"]
    assert captured["dense_limit"] == 20
    assert captured["rerank_chunk_counts"] == [4]


def test_embed_queries_preserves_query_mode_and_order(monkeypatch):
    class FakeProvider:
        def __init__(self):
            self.calls = []

        def embed_queries(self, texts):
            self.calls.append(list(texts))
            return [[float(index)] for index, _ in enumerate(texts)]

    provider = FakeProvider()
    monkeypatch.setattr(embedding_service, "_provider", lambda: provider)
    assert embedding_service.embed_queries(["q1", "q2"]) == [[0.0], [1.0]]
    assert embedding_service.embed_query("q3") == [0.0]
    assert provider.calls == [["q1", "q2"], ["q3"]]


def test_local_provider_batches_query_embed(monkeypatch):
    captured = {}

    class FakeModel:
        def query_embed(self, texts):
            captured["texts"] = list(texts)
            return [[1.0, 0.0], [0.0, 1.0]]

    provider = embedding_providers.LocalFastembedProvider.__new__(
        embedding_providers.LocalFastembedProvider
    )
    provider.model_id = "fake"
    provider.dimension = 2
    monkeypatch.setattr(embedding_providers, "_load_fastembed_model", lambda _name: FakeModel())

    assert provider.embed_queries(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["texts"] == ["first", "second"]


@pytest.mark.asyncio
async def test_stream_marks_answer_done_before_generating_suggestions(monkeypatch):
    session_id = str(uuid4())
    message_id = str(uuid4())
    persisted = {}

    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "create_session",
        lambda *_args, **_kwargs: session_id,
    )
    # HEAD's /chat/stream creates the assistant's row up front (so tool-call
    # trace steps have somewhere to be written incrementally) and fills it in
    # via finalize_message once the answer is ready -- unlike the classic
    # /chat endpoint, it never calls add_message for the assistant turn.
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "add_message",
        lambda *_args, **_kwargs: str(uuid4()),
    )
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "create_pending_message",
        lambda *_args, **_kwargs: message_id,
    )
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "get_history_for_llm",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "finalize_message",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "touch_session",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository,
        "update_message_suggestions",
        lambda mid, items: persisted.update(message_id=mid, items=items) or True,
    )
    monkeypatch.setattr(
        chat_router,
        "run_retrieval",
        lambda **_kwargs: {
            "context": "Grounded document context",
            "citations": [{"title": "Policy", "quote": "Evidence"}],
            "evidence_sufficient": True,
            "evidence_reason": None,
            "answer_mode": "analysis",
        },
    )
    monkeypatch.setattr(
        chat_router,
        "resolve_generation_target",
        lambda _model: ("openai", "fast-model", {}),
    )

    async def fake_answer_stream(**_kwargs):
        yield "Grounded "
        yield "answer"

    monkeypatch.setattr(chat_router, "generate_answer_streaming", fake_answer_stream)
    monkeypatch.setattr(
        chat_router.suggestions_service,
        "active_config",
        lambda: _cfg(),
    )
    monkeypatch.setattr(
        chat_router,
        "generate_followup_suggestions",
        lambda **_kwargs: ["Next grounded question?"],
    )

    response = await chat_router.chat_stream(
        ChatRequest(
            question="What does the document say?",
            document_ids=[uuid4()],
            # Exercises _stream_direct_events, the equivalent of the old
            # linear implementation this test was originally written
            # against -- run_retrieval/generate_answer_streaming above are
            # only wired into that path, not the default ReAct agent one.
            agent_mode="direct",
        ),
        {"id": str(uuid4()), "role": "user"},
    )
    payloads = []
    async for frame in response.body_iterator:
        text = frame.decode() if isinstance(frame, bytes) else frame
        payloads.append(json.loads(text.removeprefix("data: ").strip()))

    event_types = [payload["type"] for payload in payloads]
    assert event_types[-4:] == ["citations", "answer_done", "suggestions", "done"]
    assert payloads[-3]["suggestions_pending"] is True
    assert persisted == {
        "message_id": message_id,
        "items": ["Next grounded question?"],
    }


# ── _parse_candidates robustness (guards the truncated-JSON regression) ────────


def test_parse_candidates_valid_array():
    raw = '["Question one?", "Question two?"]'
    assert generator._parse_candidates(raw) == ["Question one?", "Question two?"]


def test_parse_candidates_strips_code_fence():
    raw = '```json\n["Q one?", "Q two?"]\n```'
    assert generator._parse_candidates(raw) == ["Q one?", "Q two?"]


def test_parse_candidates_recovers_from_missing_closing_bracket():
    # Provider truncation quirk: all strings complete, but the final "]" is dropped.
    # Must recover the complete questions instead of returning [] (the actual bug).
    raw = '[\n  "First question?",\n  "Second question?",\n  "Third question?"'
    assert generator._parse_candidates(raw) == [
        "First question?",
        "Second question?",
        "Third question?",
    ]


def test_parse_candidates_drops_trailing_partial_string():
    # Cut off mid-string: keep the complete ones, ignore the unterminated fragment.
    raw = '[\n  "Complete one?",\n  "Complete two?",\n  "Partial thi'
    assert generator._parse_candidates(raw) == ["Complete one?", "Complete two?"]
