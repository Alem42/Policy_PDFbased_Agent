import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import get_connection
from app.main import app
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.auth.repository import user_repository
from app.modules.documents.file_store import document_file_store
from app.modules.documents.repositories import tasks as task_module
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.tasks import ActiveDocumentTask, LostTaskLease
from app.modules.documents.repositories.tasks import document_task_repository as tasks
from app.modules.documents.service import pipeline
from app.modules.documents.upload_registration import IdempotencyConflict
from app.modules.embedding import service as embedding
from app.modules.embedding.providers import LocalFastembedProvider
from app.modules.embedding.settings import EmbeddingConfig

pytestmark = pytest.mark.integration


@pytest.fixture
def scenario(postgres_repository, monkeypatch, tmp_path):
    actor = user_repository.create(
        f"stage2-{uuid4().hex}", f"{uuid4().hex}@example.test", "unused", "admin"
    )
    monkeypatch.setattr(document_file_store, "_document_dir", lambda: tmp_path)
    monkeypatch.setattr(document_file_store, "relative_path", lambda path: str(path))
    settings = Settings(_env_file=None, document_task_retry_seconds=0)
    monkeypatch.setattr(task_module, "get_settings", lambda: settings)
    config = EmbeddingConfig()
    monkeypatch.setattr(
        embedding, "_cache", {"config": config, "provider": LocalFastembedProvider(config)}
    )
    # SQL, files, extraction and chunking are real; model providers are controlled here.
    monkeypatch.setattr(embedding, "embed_documents", lambda texts: [[0.1] * 384 for _ in texts])
    monkeypatch.setattr(
        pipeline, "generate_document_metadata", lambda **kw: ({"title": "Test policy"}, None)
    )
    monkeypatch.setattr(
        pipeline, "build_contextual_headers", lambda chunks, **kw: [""] * len(chunks)
    )
    created = []

    async def upload(content=None, key=None, **kwargs):
        data = (
            content
            or (
                "Software test policy. Flood grant applicants must submit evidence within 14 days. "
                f"Public warnings are sent every six hours. Reference {uuid4().hex}.\n\n"
            ).encode()
            * 8
        )
        row = await pipeline.save_upload(
            UploadFile(filename="policy.txt", file=io.BytesIO(data)),
            durable=True,
            imported_by=str(actor["id"]),
            idempotency_key=key,
            **kwargs,
        )
        created.append(row["id"])
        return row

    yield upload, tmp_path, str(actor["id"])
    with get_connection() as conn:
        conn.execute("DELETE FROM documents WHERE imported_by = %s", (actor["id"],))
        conn.execute("DELETE FROM app_users WHERE id = %s", (actor["id"],))


def counts(document_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT (SELECT count(*) FROM document_pages WHERE document_id = %s) AS pages, "
            "(SELECT count(*) FROM document_chunks WHERE document_id = %s) AS chunks, "
            "(SELECT count(*) FROM chunk_embeddings e JOIN document_chunks c ON c.id=e.chunk_id "
            "WHERE c.document_id = %s) AS vectors",
            (document_id,) * 3,
        ).fetchone()


async def test_document_task_and_request_rollback_together(scenario, monkeypatch):
    upload, storage, actor = scenario

    def fail(*args, **kwargs):
        raise RuntimeError("Task insert deliberately failed")

    monkeypatch.setattr(tasks, "enqueue", fail)
    with pytest.raises(RuntimeError, match="Task insert"):
        await upload(key="transaction-test", metadata={"title": "Must roll back"})
    with get_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM documents WHERE imported_by=%s", (actor,)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM document_upload_requests WHERE actor_id=%s", (actor,)
            ).fetchone()["n"]
            == 0
        )
    assert not [path for path in storage.rglob("*") if path.is_file()]


async def test_concurrent_same_request_returns_same_document_and_task(scenario):
    upload, storage, _ = scenario
    content = f"Idempotent upload, actual policy text {uuid4().hex}".encode()
    first, second = await asyncio.gather(
        upload(content, "same-request"), upload(content, "same-request")
    )
    assert first["id"] == second["id"]
    assert first["task_id"] == second["task_id"]
    assert sorted([first["replayed"], second["replayed"]]) == [False, True]
    with get_connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM document_tasks WHERE document_id=%s", (first["id"],)
            ).fetchone()["n"]
            == 1
        )
    assert len([p for p in storage.rglob("*") if p.is_file()]) == 1
    with pytest.raises(IdempotencyConflict):
        await upload(b"Different intent and different content", "same-request")


async def test_same_request_key_with_changed_metadata_conflicts(scenario):
    upload, _, _ = scenario
    content = b"Identical file but two different titles."
    await upload(content, "metadata-key", metadata={"title": "First"})
    with pytest.raises(IdempotencyConflict):
        await upload(content, "metadata-key", metadata={"title": "Second"})


async def test_two_workers_cannot_claim_same_task(scenario):
    upload, _, _ = scenario
    row = await upload()
    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(tasks.claim, ["worker-a", "worker-b"]))
    claimed = [task for task in results if task]
    assert len(claimed) == 1
    assert str(claimed[0]["id"]) == row["task_id"]


async def test_skip_locked_avoids_waiting_for_first_queued_task(scenario):
    upload, _, _ = scenario
    first, second = await upload(), await upload()
    with get_connection() as conn:
        conn.execute("SELECT id FROM document_tasks WHERE id=%s FOR UPDATE", (first["task_id"],))
        with ThreadPoolExecutor(1) as workers:
            claimed = workers.submit(tasks.claim, "skip-locked-worker").result(timeout=2)
    assert str(claimed["id"]) == second["task_id"]


async def test_stale_worker_cannot_publish_after_reclaim(scenario, monkeypatch):
    upload, _, _ = scenario
    row = await upload()
    first = tasks.claim("old-worker")
    recovered = []

    def finish_computation_after_expiry(texts):
        with get_connection() as conn:
            conn.execute(
                "UPDATE document_tasks SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
                (first["id"],),
            )
        recovered.append(tasks.claim("new-worker"))
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr(embedding, "embed_documents", finish_computation_after_expiry)
    with pytest.raises(LostTaskLease):
        pipeline.execute_document_task(first)
    assert dict(counts(row["id"])) == {"pages": 0, "chunks": 0, "vectors": 0}
    assert not tasks.heartbeat(first)
    monkeypatch.setattr(embedding, "embed_documents", lambda texts: [[0.1] * 384 for _ in texts])
    pipeline.execute_document_task(recovered[0])
    published = dict(counts(row["id"]))
    assert published["pages"] == 1 and published["chunks"] > 0
    assert published["vectors"] == published["chunks"]
    assert tasks.for_document(row["id"])["status"] == "succeeded"
    with pytest.raises(LostTaskLease):
        pipeline.execute_document_task(recovered[0])
    assert dict(counts(row["id"])) == published


async def test_failed_final_commit_preserves_previous_index(scenario, monkeypatch):
    upload, _, _ = scenario
    row = await upload()
    pipeline.execute_document_task(tasks.claim("first"))
    before = dict(counts(row["id"]))
    tasks.enqueue(row["id"])
    attempt = tasks.claim("rescan")

    def fail(*args, **kwargs):
        raise RuntimeError("Injected error before final commit")

    monkeypatch.setattr(pipeline.processing_job_repository, "finish", fail)
    with pytest.raises(RuntimeError, match="before final commit"):
        pipeline.execute_document_task(attempt)
    assert dict(counts(row["id"])) == before
    assert tasks.for_document(row["id"])["status"] == "running"
    tasks.fail(attempt, RuntimeError("Retry required"))
    assert tasks.for_document(row["id"])["status"] == "queued"


async def test_retry_budget_and_manual_retry_keep_attempt_history(scenario):
    upload, _, _ = scenario
    row = await upload()
    for attempt in range(1, 4):
        task = tasks.claim("failing-worker")
        assert task["attempts"] == attempt
        tasks.fail(task, ValueError("Invalid document content"))
    assert tasks.for_document(row["id"])["status"] == "failed"
    assert tasks.claim("nothing-left") is None
    retried = tasks.retry(row["task_id"])
    assert retried["attempts"] == 3 and retried["max_attempts"] == 6
    assert tasks.retry(row["task_id"])["max_attempts"] == 6
    pipeline.execute_document_task(tasks.claim("repaired-worker"))
    assert tasks.for_document(row["id"])["status"] == "succeeded"


async def test_final_attempt_crash_is_terminal(scenario):
    upload, _, _ = scenario
    row = await upload()
    with get_connection() as conn:
        conn.execute("UPDATE document_tasks SET max_attempts=1 WHERE id=%s", (row["task_id"],))
    task = tasks.claim("crashed")
    with get_connection() as conn:
        conn.execute(
            "UPDATE document_tasks SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
            (task["id"],),
        )
    assert tasks.claim("replacement") is None
    assert tasks.for_document(row["id"])["status"] == "failed"
    assert document_repository.get_record(row["id"])["status"] == "failed"


async def test_heartbeat_renews_only_unexpired_current_claim(scenario):
    upload, _, _ = scenario
    await upload()
    task = tasks.claim("heartbeat-worker")
    with get_connection() as conn:
        conn.execute(
            "UPDATE document_tasks SET lease_expires_at=now()+interval '2 seconds' WHERE id=%s",
            (task["id"],),
        )
    assert tasks.heartbeat(task)
    renewed = tasks.for_document(str(task["document_id"]))
    assert renewed["lease_expires_at"] > task["lease_expires_at"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE document_tasks SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
            (task["id"],),
        )
    assert not tasks.heartbeat(task)
    replacement = tasks.claim("replacement")
    assert replacement["lease_token"] != task["lease_token"]
    assert not tasks.heartbeat(task)


async def test_upload_http_replays_and_rejects_changed_intent(scenario):
    _, _, actor = scenario
    app.dependency_overrides[require_admin] = lambda: {"id": actor, "role": "admin"}
    try:
        # Fixture owns the DB lifecycle; external-process tests cover app startup.
        with closing(TestClient(app)) as client:
            arguments = {
                "headers": {"Idempotency-Key": "http-retry"},
                "files": {"file": ("policy.txt", b"Real uploaded policy text")},
            }
            first = client.post("/api/v1/admin/documents", **arguments)
            second = client.post("/api/v1/admin/documents", **arguments)
            changed = client.post("/api/v1/admin/documents", **arguments, data={"title": "Changed"})
        assert first.status_code == second.status_code == 202
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["task_id"] == second.json()["task_id"]
        assert second.headers["Idempotency-Replayed"] == "true"
        assert changed.status_code == 409
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_task_operations_are_admin_only():
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/document-tasks").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: {"id": "user", "role": "user"}
        try:
            assert client.get("/api/v1/admin/document-tasks").status_code == 403
            assert client.post(f"/api/v1/admin/document-tasks/{uuid4()}/retry").status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)


async def test_active_tasks_coalesce_but_different_operations_conflict(scenario):
    upload, _, _ = scenario
    row = await upload()
    assert str(tasks.enqueue(row["id"])["id"]) == row["task_id"]
    with pytest.raises(ActiveDocumentTask):
        tasks.enqueue(row["id"], "reembed")


async def test_reembed_retry_preserves_chunks_and_returns_to_embedding_state(scenario):
    upload, _, _ = scenario
    row = await upload()
    pipeline.execute_document_task(tasks.claim("ingest"))
    before = dict(counts(row["id"]))
    with get_connection() as conn:
        chunk_ids = conn.execute(
            "SELECT id FROM document_chunks WHERE document_id=%s ORDER BY id", (row["id"],)
        ).fetchall()
    tasks.enqueue(row["id"], "reembed")
    attempt = tasks.claim("reembed-failure")
    tasks.fail(attempt, RuntimeError("Transient model error"))
    assert document_repository.get_record(row["id"])["status"] == "annotated"
    pipeline.execute_document_task(tasks.claim("reembed-retry"))
    assert tasks.for_document(row["id"])["status"] == "succeeded"
    assert dict(counts(row["id"])) == before
    with get_connection() as conn:
        assert (
            conn.execute(
                "SELECT id FROM document_chunks WHERE document_id=%s ORDER BY id", (row["id"],)
            ).fetchall()
            == chunk_ids
        )
