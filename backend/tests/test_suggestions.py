from __future__ import annotations

from app.modules.chat.suggestions import generator
from app.modules.chat.suggestions.config import SuggestionConfig


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


def _patch(monkeypatch, candidates, distances, reranker=5.0):
    """Stub the LLM proposal + retrieval so tests need no network/DB."""
    monkeypatch.setattr(generator, "_propose_candidates", lambda **kw: list(candidates))
    monkeypatch.setattr(generator, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(generator, "min_reranker_score", lambda: -7.0)
    captured: dict = {"questions": []}

    def fake_retrieve(question, identifiers, limit=8, include_restricted=False):
        captured["last_identifiers"] = identifiers
        captured["questions"].append(question)
        distance = distances.get(question, 1.0)  # unknown -> off-topic
        return [{"distance": distance, "reranker_score": reranker}]

    monkeypatch.setattr(generator, "retrieve_relevant_chunks", fake_retrieve)
    return captured


def test_only_answerable_candidates_survive(monkeypatch):
    candidates = ["Q good1", "Q bad1", "Q good2", "Q bad2", "Q good3"]
    distances = {"Q good1": 0.2, "Q good2": 0.3, "Q good3": 0.25}  # bad* -> 1.0 (fail)
    _patch(monkeypatch, candidates, distances)

    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="some context",
        identifiers=["d1"], config=_cfg(max_suggestions=2),
    )
    # Only distance-passing candidates, capped at max_suggestions, order preserved.
    assert out == ["Q good1", "Q good2"]


def test_disabled_returns_empty(monkeypatch):
    _patch(monkeypatch, ["Q good1"], {"Q good1": 0.1})
    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="ctx",
        identifiers=["d1"], config=_cfg(enabled=False),
    )
    assert out == []


def test_llm_error_returns_empty(monkeypatch):
    def boom(**kw):
        raise RuntimeError("llm down")

    monkeypatch.setattr(generator, "_propose_candidates", boom)
    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="ctx", identifiers=["d1"], config=_cfg(),
    )
    assert out == []


def test_reranker_floor_rejects_off_topic(monkeypatch):
    # Distance passes but the reranker score is below the floor -> rejected.
    _patch(monkeypatch, ["Q1"], {"Q1": 0.2}, reranker=-9.0)
    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="ctx", identifiers=["d1"], config=_cfg(),
    )
    assert out == []


def test_dedupes_original_and_history(monkeypatch):
    candidates = ["What are the pillars?", "Already asked before"]
    distances = {"What are the pillars?": 0.1, "Already asked before": 0.1}
    _patch(monkeypatch, candidates, distances)
    out = generator.generate_followup_suggestions(
        question="What are the pillars?", answer="ans", context="ctx",
        identifiers=["d1"],
        history=[{"role": "user", "content": "Already asked before"}],
        config=_cfg(max_suggestions=3),
    )
    # One equals the original question, one repeats history -> both dropped.
    assert out == []


def test_multifile_forwards_all_identifiers(monkeypatch):
    identifiers = [f"doc-{i}" for i in range(12)]
    captured = _patch(monkeypatch, ["Q1"], {"Q1": 0.1})
    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="ctx",
        identifiers=identifiers, config=_cfg(max_suggestions=1),
    )
    assert out == ["Q1"]
    assert captured["last_identifiers"] == identifiers  # all 12 reach retrieval


def test_validation_distance_override_is_stricter(monkeypatch):
    # Candidate at distance 0.4 passes the gate default (0.45) but fails a 0.3 override.
    _patch(monkeypatch, ["Q1"], {"Q1": 0.4})
    out = generator.generate_followup_suggestions(
        question="original", answer="ans", context="ctx",
        identifiers=["d1"], config=_cfg(validation_distance=0.3),
    )
    assert out == []
