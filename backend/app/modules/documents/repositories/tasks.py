"""Durable scheduling, short claims, renewable leases, and fenced publication."""

import json
from contextlib import contextmanager
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import get_connection


class LostTaskLease(RuntimeError):
    """An expired/replaced worker must discard its computed result."""


class ActiveDocumentTask(ValueError):
    pass


class DocumentTaskRepository:
    def enqueue(self, document_id: str, task_type: str = "ingest", *, connection=None) -> dict:
        if connection is None:
            with get_connection() as conn:
                return self.enqueue(document_id, task_type, connection=conn)
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"document-task:{document_id}",),
        )
        existing = connection.execute(
            "SELECT * FROM document_tasks WHERE document_id = %s "
            "AND status IN ('queued', 'running')",
            (document_id,),
        ).fetchone()
        if existing:
            if existing["task_type"] != task_type:
                raise ActiveDocumentTask("This document already has a different active task.")
            return dict(existing)
        task = connection.execute(
            "INSERT INTO document_tasks (id, document_id, task_type, max_attempts) "
            "VALUES (%s, %s, %s, %s) RETURNING *",
            (str(uuid4()), document_id, task_type, get_settings().document_task_max_attempts),
        ).fetchone()
        connection.execute(
            "UPDATE documents SET status = %s, error_message = NULL WHERE id = %s",
            ("annotated" if task_type == "reembed" else "uploaded", document_id),
        )
        return dict(task)

    def claim(self, worker_id: str) -> dict | None:
        with get_connection() as conn:
            expired = conn.execute(
                """
                WITH exhausted AS (
                    SELECT id FROM document_tasks WHERE status = 'running'
                    AND lease_expires_at <= clock_timestamp() AND attempts >= max_attempts
                    ORDER BY lease_expires_at FOR UPDATE SKIP LOCKED LIMIT 20
                )
                UPDATE document_tasks t SET status = 'failed', finished_at = now(),
                    updated_at = now(), lease_token = NULL, lease_expires_at = NULL,
                    last_error = 'Worker lease expired on the final permitted attempt.'
                FROM exhausted e WHERE t.id = e.id RETURNING t.document_id, t.last_error
                """
            ).fetchall()
            for row in expired:
                conn.execute(
                    "UPDATE documents SET status = 'failed', error_message = %s WHERE id = %s",
                    (row["last_error"], row["document_id"]),
                )
            task = conn.execute(
                """
                WITH candidate AS (
                    SELECT id FROM document_tasks
                    WHERE attempts < max_attempts AND (
                        (status = 'queued' AND available_at <= clock_timestamp()) OR
                        (status = 'running' AND lease_expires_at <= clock_timestamp())
                    )
                    ORDER BY available_at, created_at, id
                    FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE document_tasks t SET status = 'running', attempts = attempts + 1,
                    worker_id = %s, lease_token = %s,
                    lease_expires_at = clock_timestamp() + %s * interval '1 second',
                    heartbeat_at = clock_timestamp(), updated_at = now(),
                    last_error = CASE WHEN t.status = 'running'
                        THEN 'Previous worker lease expired; task reclaimed.' ELSE last_error END
                FROM candidate c WHERE t.id = c.id RETURNING t.*
                """,
                (worker_id, str(uuid4()), get_settings().document_task_lease_seconds),
            ).fetchone()
            if task and task["attempts"] > 1:
                conn.execute(
                    "UPDATE processing_jobs SET status = 'failed', finished_at = now(), "
                    "error_message = 'Previous task attempt interrupted before completion.' "
                    "WHERE document_id = %s AND status = 'running'",
                    (task["document_id"],),
                )
        return dict(task) if task else None

    @contextmanager
    def owned(self, task: dict):
        """Lock only for a short SQL transaction; never hold across model/OCR I/O."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM document_tasks WHERE id = %s AND status = 'running' "
                "AND lease_token = %s AND lease_expires_at > clock_timestamp() FOR UPDATE",
                (task["id"], task["lease_token"]),
            ).fetchone()
            if not row:
                raise LostTaskLease("Task lease was lost; stale worker result discarded.")
            yield conn

    def heartbeat(self, task: dict) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE document_tasks SET heartbeat_at = clock_timestamp(), updated_at = now(),
                    lease_expires_at = clock_timestamp() + %s * interval '1 second'
                WHERE id = %s AND status = 'running' AND lease_token = %s
                    AND lease_expires_at > clock_timestamp() RETURNING id
                """,
                (get_settings().document_task_lease_seconds, task["id"], task["lease_token"]),
            ).fetchone()
        return row is not None

    def progress(self, task: dict, status: str) -> None:
        with self.owned(task) as conn:
            conn.execute(
                "UPDATE documents SET status = %s, error_message = NULL WHERE id = %s",
                (status, task["document_id"]),
            )

    def succeed(self, task: dict, result: dict, *, connection) -> None:
        # Caller holds owned(task), together with all result writes in this transaction.
        connection.execute(
            """
            UPDATE document_tasks SET status = 'succeeded', result_json = %s::jsonb,
                finished_at = now(), updated_at = now(), lease_token = NULL,
                lease_expires_at = NULL, last_error = NULL
            WHERE id = %s AND lease_token = %s AND status = 'running'
            """,
            (json.dumps(result), task["id"], task["lease_token"]),
        )

    def fail(self, task: dict, error: Exception) -> None:
        settings = get_settings()
        with self.owned(task) as conn:
            retry = task["attempts"] < task["max_attempts"]
            delay = min(settings.document_task_retry_seconds * 2 ** (task["attempts"] - 1), 60)
            message = str(error)[:2000] or type(error).__name__
            conn.execute(
                """
                UPDATE document_tasks SET status = %s, last_error = %s,
                    available_at = clock_timestamp() + %s * interval '1 second',
                    updated_at = now(), finished_at = CASE WHEN %s THEN NULL ELSE now() END,
                    lease_token = NULL, lease_expires_at = NULL
                WHERE id = %s
                """,
                ("queued" if retry else "failed", message, delay, retry, task["id"]),
            )
            conn.execute(
                "UPDATE documents SET status = %s, error_message = %s WHERE id = %s",
                (
                    ("annotated" if task["task_type"] == "reembed" else "uploaded")
                    if retry
                    else "failed",
                    message,
                    task["document_id"],
                ),
            )

    def retry(self, task_id: str) -> dict:
        with get_connection() as conn:
            task = conn.execute("SELECT * FROM document_tasks WHERE id = %s", (task_id,)).fetchone()
            if not task:
                raise FileNotFoundError("Document task not found.")
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"document-task:{task['document_id']}",),
            )
            task = conn.execute(
                "SELECT * FROM document_tasks WHERE id = %s FOR UPDATE", (task_id,)
            ).fetchone()
            if task["status"] in {"queued", "running"}:
                return dict(task)
            if task["status"] != "failed":
                raise ActiveDocumentTask("Only failed tasks can be retried.")
            active = conn.execute(
                "SELECT id FROM document_tasks WHERE document_id = %s "
                "AND status IN ('queued', 'running')",
                (task["document_id"],),
            ).fetchone()
            if active:
                raise ActiveDocumentTask("This document already has an active task.")
            task = conn.execute(
                """
                UPDATE document_tasks SET status = 'queued', available_at = now(),
                    max_attempts = attempts + %s, finished_at = NULL, updated_at = now()
                WHERE id = %s RETURNING *
                """,
                (get_settings().document_task_max_attempts, task_id),
            ).fetchone()
            conn.execute(
                "UPDATE documents SET status = %s, error_message = NULL WHERE id = %s",
                (
                    "annotated" if task["task_type"] == "reembed" else "uploaded",
                    task["document_id"],
                ),
            )
        return dict(task)

    def for_document(self, document_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM document_tasks WHERE document_id = %s "
                "ORDER BY (status IN ('queued', 'running')) DESC, updated_at DESC, id DESC LIMIT 1",
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def queue_position(self, task: dict) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT count(*) AS n FROM document_tasks WHERE status = 'queued' "
                "AND (available_at, created_at, id) <= (%s, %s, %s)",
                (task["available_at"], task["created_at"], task["id"]),
            ).fetchone()
        return int(row["n"])

    def list(self, limit: int = 50) -> dict:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT t.*, d.original_filename FROM document_tasks t "
                "JOIN documents d ON d.id = t.document_id "
                "ORDER BY t.created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
            counts = conn.execute(
                "SELECT status, count(*) AS count FROM document_tasks GROUP BY status"
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "counts": {row["status"]: row["count"] for row in counts},
        }


document_task_repository = DocumentTaskRepository()
