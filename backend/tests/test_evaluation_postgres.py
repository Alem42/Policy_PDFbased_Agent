from uuid import uuid4

import pytest

from app.core.database import get_connection
from app.modules.auth.repository import user_repository
from app.modules.evaluation import repository
from app.modules.evaluation.config import Review

pytestmark = pytest.mark.integration


async def test_corpus_import_is_idempotent_and_preserves_test_tags(
    postgres_repository, tmp_path, monkeypatch
):
    from app.modules.documents.file_store import document_file_store
    from app.modules.documents.repositories.content import document_content_repository
    from app.modules.evaluation import corpus

    original = corpus.manifest()
    one = {**original, "documents": original["documents"][:1]}
    monkeypatch.setattr(corpus, "manifest", lambda: one)
    monkeypatch.setattr(document_file_store, "_document_dir", lambda: tmp_path)
    monkeypatch.setattr(document_file_store, "relative_path", lambda path: str(path))
    actor = user_repository.create(
        f"corpus-{uuid4().hex}", f"{uuid4().hex}@example.test", "unused", "admin"
    )
    identifier = None
    try:
        first = await corpus.install(str(actor["id"]))
        identifier = first["documents"][0]["document_id"]
        document_content_repository.update_metadata(
            identifier, {"keywords": ["user-added-tag"], "title": "User reviewed title"}
        )
        second = await corpus.install(str(actor["id"]))
        assert second["documents"][0]["document_id"] == identifier
        assert second["documents"][0]["reused"] is True
        assert corpus.mapping()[original["documents"][0]["id"]] == identifier
        with get_connection() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM documents WHERE id=%s", (identifier,)
                ).fetchone()["n"]
                == 1
            )
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM document_tasks WHERE document_id=%s", (identifier,)
                ).fetchone()["n"]
                == 1
            )
            tags = conn.execute(
                "SELECT keywords FROM document_metadata WHERE document_id=%s", (identifier,)
            ).fetchone()["keywords"]
            assert {"test-corpus", "user-added-tag"} <= set(tags)
            assert (
                conn.execute(
                    "SELECT title FROM document_metadata WHERE document_id=%s", (identifier,)
                ).fetchone()["title"]
                == "User reviewed title"
            )
    finally:
        with get_connection() as conn:
            if identifier:
                conn.execute("DELETE FROM documents WHERE id=%s", (identifier,))
            conn.execute("DELETE FROM app_users WHERE id=%s", (actor["id"],))


def test_run_lease_resume_review_and_cancellation(postgres_repository):
    actor = user_repository.create(
        f"eval-{uuid4().hex}", f"{uuid4().hex}@example.test", "unused", "admin"
    )
    identifier = repository.create(
        {"model": "test"}, {"version": 1}, [{"id": "case"}], str(actor["id"])
    )
    try:
        run = repository.claim()
        assert str(run["id"]) == identifier
        assert repository.claim() is None
        assert repository.heartbeat(run)
        repository.record(
            run, {"case_id": "case", "status": "completed", "answer": "output"}, {"completed": 1}
        )
        repository.release(run)
        resumed = repository.claim()
        assert resumed["lease_token"] != run["lease_token"]
        assert resumed["results"]["case"]["answer"] == "output"
        with pytest.raises(RuntimeError, match="lease"):
            repository.record(run, {"case_id": "case"}, {})
        repository.review(
            identifier, "case", Review(score=4, comment="Verified source page"), str(actor["id"])
        )
        assert repository.get(identifier)["reviews"][0]["score"] == 4
        repository.cancel(identifier)
        assert not repository.heartbeat(resumed)
        repository.finish(resumed)
        assert repository.get(identifier)["status"] == "cancelled"
        assert repository.recent()[0]["completed"] == 1
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM evaluation_runs WHERE id=%s", (identifier,))
            conn.execute("DELETE FROM app_users WHERE id=%s", (actor["id"],))


def test_experiment_artifacts_and_trials_reject_cancelled_writer(postgres_repository):
    from app.modules.evaluation import lab_repository as lab

    actor = user_repository.create(
        f"lab-{uuid4().hex}", f"{uuid4().hex}@example.test", "unused", "admin"
    )
    identifier = repository.create({}, {}, [{"id": "case"}], str(actor["id"]))
    try:
        run = repository.claim()
        assert str(run["id"]) == identifier
        lab.artifact(run, "proof", {"n": 1})
        lab.trial(run, "variant", "case", {"case_id": "case"})
        assert lab.artifacts(identifier)["proof"] == {"n": 1}
        assert len(lab.trials(identifier)) == 1
        repository.cancel(identifier)
        with pytest.raises(RuntimeError, match="cancelled|lease"):
            lab.artifact(run, "proof", {"n": 2})
        with pytest.raises(RuntimeError, match="cancelled|lease"):
            lab.trial(run, "variant", "case", {"case_id": "overwritten"})
        assert lab.artifacts(identifier)["proof"] == {"n": 1}
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM evaluation_runs WHERE id=%s", (identifier,))
            conn.execute("DELETE FROM app_users WHERE id=%s", (actor["id"],))


def test_lab_index_writes_do_not_modify_production_chunks(postgres_repository, monkeypatch):
    from app.modules.evaluation import experiments

    monkeypatch.setattr(
        experiments.embedding, "active_model_id", lambda: experiments.EMBEDDING_MODEL
    )
    monkeypatch.setattr(experiments.embedding, "active_dimension", lambda: 1024)
    monkeypatch.setattr(experiments.embedding, "count_tokens", len)
    monkeypatch.setattr(experiments, "model_revision", lambda: "isolated-test")
    monkeypatch.setattr(
        experiments.embedding,
        "embed_documents",
        lambda texts: [[1.0] + [0.0] * 1023 for _ in texts],
    )
    with get_connection() as conn:
        before = conn.execute("SELECT id FROM document_chunks ORDER BY id").fetchall()
    identifier = None
    try:
        pages = {f"test-{uuid4()}": [{"page": 1, "text": "source paragraph " * 12}]}
        identifier, stats = experiments.build_index(pages, 64, 8)
        assert stats["max_chunk_tokens"] <= 64
        rows, vectors = experiments.load_index(identifier)
        assert len(rows) == stats["chunks"] and vectors.shape == (len(rows), 1024)
        cached, _ = experiments.build_index(pages, 64, 8)
        assert cached == identifier
        with get_connection() as conn:
            after = conn.execute("SELECT id FROM document_chunks ORDER BY id").fetchall()
        assert after == before
    finally:
        if identifier:
            with get_connection() as conn:
                conn.execute("DELETE FROM evaluation_indexes WHERE id=%s", (identifier,))


def test_continuation_skips_outputs_from_earlier_batches(postgres_repository):
    actor = user_repository.create(
        f"reuse-{uuid4().hex}", f"{uuid4().hex}@example.test", "unused", "admin"
    )
    root = repository.create({}, {}, [{"id": "a"}, {"id": "b"}], str(actor["id"]))
    child = repository.create({"reuse_run_id": root}, {}, [{"id": "b"}], str(actor["id"]))
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE evaluation_runs SET results=%s::jsonb WHERE id=%s",
                ('{"a":{"status":"completed"}}', root),
            )
            conn.execute(
                "UPDATE evaluation_runs SET results=%s::jsonb WHERE id=%s",
                ('{"b":{"status":"completed"},"failed":{"status":"error"}}', child),
            )
        assert repository.completed_case_ids(root) == {"a", "b"}
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM evaluation_runs WHERE id=ANY(%s::uuid[])", ([root, child],))
            conn.execute("DELETE FROM app_users WHERE id=%s", (actor["id"],))
