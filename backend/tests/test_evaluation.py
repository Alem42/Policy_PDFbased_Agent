from unittest.mock import Mock

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import require_admin
from app.modules.evaluation import corpus, repository, runner, service
from app.modules.evaluation.config import EvaluationConfig
from app.modules.evaluation.metrics import aggregate, citation_metrics, evidence_metrics, normalized


def test_pack_checksums_and_page_anchors():
    files = corpus.verified_files()
    assert len(files) == 12
    by_source = {e["id"]: path for e, path in files}
    seen = set()
    for case in corpus.cases():
        assert case["id"] not in seen
        seen.add(case["id"])
        assert set(case["source_ids"]) <= by_source.keys()
        assert case["expected_allow"] == bool(case["evidence"])
        for anchor in case["evidence"]:
            with fitz.open(by_source[anchor["source_id"]]) as pdf:
                assert normalized(anchor["quote"]) in normalized(pdf[anchor["page"] - 1].get_text())
    assert len(seen) == 27


def test_pack_rejects_tampered_file_before_import(tmp_path, monkeypatch):
    (tmp_path / "bad.pdf").write_bytes(b"tampered")
    monkeypatch.setattr(corpus, "CORPUS", tmp_path)
    monkeypatch.setattr(
        corpus,
        "manifest",
        lambda: {"documents": [{"id": "bad", "local_path": "bad.pdf", "sha256": "0" * 64}]},
    )
    with pytest.raises(ValueError, match="checksum"):
        corpus.verified_files()


def test_evidence_recall_requires_source_page_and_exact_anchor():
    gold = [
        {"source_id": "a", "page": 2, "quote": "43% below 2005"},
        {"source_id": "a", "page": 3, "quote": "zero by 2050"},
    ]
    chunks = [{"document_id": "d", "page_start": 2, "page_end": 2, "text": "43% below 2005"}]
    assert evidence_metrics(gold, chunks, {"a": "d"}) == {"evidence_recall_at_k": 0.5, "mrr": 1}
    assert evidence_metrics(gold, chunks, {"a": "wrong"})["evidence_recall_at_k"] == 0
    assert evidence_metrics([], chunks, {})["evidence_recall_at_k"] is None


def test_citations_validate_scope_page_quote_and_marker():
    citations = [{"chunk_id": "c", "document_id": "d", "page": 2, "quote": "source text"}]
    stored = [{"id": "c", "document_id": "d", "page_start": 2, "text": "original source text"}]
    assert citation_metrics("Answer [1]", citations, stored, ["d"])["citation_integrity"] == 1
    assert citation_metrics("Answer [1, 2]", citations, stored, ["d"])["citation_integrity"] == 0.5
    assert citation_metrics("Answer [1]", citations, stored, ["other"])["citation_integrity"] == 0
    assert citation_metrics("No citations", citations, stored, ["d"])["citation_integrity"] is None
    citations[0]["page"] = 9
    assert citation_metrics("Answer [1]", citations, stored, ["d"])["invalid_citation_markers"] == 1


def test_aggregate_does_not_score_missing_or_errors_as_success():
    assert aggregate([])["balanced_gate_accuracy"] is None
    assert aggregate([{"status": "error"}])["errors"] == 1
    positive = {
        "status": "completed",
        "expected_allow": True,
        "actual_allow": False,
        "evidence_recall_at_k": 0,
        "mrr": 0,
        "total_ms": 100,
        "has_citations": False,
    }
    assert aggregate([positive])["high_evidence_allow_rate"] == 0
    assert aggregate([positive])["low_evidence_block_rate"] is None
    negative = {**positive, "expected_allow": False}
    assert aggregate([positive, negative])["balanced_gate_accuracy"] == 0.5


def test_unknown_case_rejected_before_any_llm_or_database(monkeypatch):
    create = Mock(side_effect=AssertionError("must not enqueue"))
    monkeypatch.setattr(repository, "create", create)
    with pytest.raises(ValueError, match="Unknown"):
        service.start_run(EvaluationConfig(case_ids=["nonexistent"]), "actor")
    create.assert_not_called()


def test_evaluation_endpoints_require_admin():
    client = TestClient(app)
    assert client.get("/api/v1/admin/evaluation").status_code == 401
    assert client.post("/api/v1/admin/evaluation/corpus").status_code == 401
    assert client.post("/api/v1/admin/evaluation/unload").status_code == 401
    assert client.put("/api/v1/admin/evaluation/validation", json={}).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/evaluation/runs/00000000-0000-0000-0000-000000000000/apply"
        ).status_code
        == 401
    )


def test_evaluation_request_and_missing_run_validation(monkeypatch):
    app.dependency_overrides[require_admin] = lambda: {"id": "actor", "role": "admin"}
    try:
        client = TestClient(app)
        assert client.post("/api/v1/admin/evaluation/runs", json={"top_k": 0}).status_code == 422
        assert client.get("/api/v1/admin/evaluation/runs/not-a-uuid").status_code == 422
        monkeypatch.setattr(repository, "get", Mock(side_effect=LookupError("missing")))
        assert (
            client.get(
                "/api/v1/admin/evaluation/runs/00000000-0000-0000-0000-000000000000"
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(require_admin, None)


async def test_index_change_blocks_mixed_run_publication(monkeypatch):
    run = {
        "id": "run",
        "lease_token": "t",
        "cases": [{"id": "case", "source_ids": ["source"]}],
        "snapshot": {"version": 1},
        "config": {},
        "results": {},
    }
    monkeypatch.setattr(repository, "heartbeat", lambda *a: True)
    monkeypatch.setattr(runner, "snapshot", lambda *a: {"version": 2})
    finish = Mock()
    execute = Mock(side_effect=AssertionError("Must not infer on changed index"))
    monkeypatch.setattr(repository, "finish", finish)
    monkeypatch.setattr(runner, "run_case", execute)
    await service.EvaluationWorker()._execute(run)
    assert finish.call_args.args[1] == "failed"
    execute.assert_not_called()


async def test_resumed_run_does_not_repeat_completed_cases(monkeypatch):
    case = {"id": "done", "source_ids": ["source"]}
    run = {"id": "run", "lease_token": "t", "cases": [case], "results": {"done": {}}}
    finish = Mock()
    monkeypatch.setattr(repository, "finish", finish)
    monkeypatch.setattr(runner, "run_case", Mock(side_effect=AssertionError("Already complete")))
    await service.EvaluationWorker()._execute(run)
    finish.assert_called_once_with(run)
