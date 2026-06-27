import json
from uuid import uuid4

from app.core.database import get_connection


class ProcessingJobRepository:
    """Persistence boundary for document processing jobs."""

    def start(self, document_id: str, job_type: str) -> str:
        job_id = str(uuid4())
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO processing_jobs (id, document_id, job_type, status)
                VALUES (%s, %s, %s, 'running')
                """,
                (job_id, document_id, job_type),
            )
            connection.commit()
        return job_id

    def finish(
        self,
        job_id: str,
        *,
        status: str = "completed",
        error_message: str | None = None,
        details: dict | None = None,
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE processing_jobs
                SET status = %s, finished_at = now(), error_message = %s,
                    details_json = %s::jsonb
                WHERE id = %s
                """,
                (status, error_message, json.dumps(details or {}), job_id),
            )
            connection.commit()

    def list_for_document(self, document_id: str, limit: int = 10) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT job_type, status, started_at, finished_at,
                    error_message, details_json
                FROM processing_jobs WHERE document_id = %s
                ORDER BY started_at DESC LIMIT %s
                """,
                (document_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


processing_job_repository = ProcessingJobRepository()
