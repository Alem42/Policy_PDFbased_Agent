"""Persistence for permanent web-document lifecycle policy."""

from __future__ import annotations

from datetime import datetime

from app.core.database import get_connection


class WebGovernanceRepository:
    def register_import(self, document_id: str, *, created_by: str | None) -> dict:
        with get_connection() as connection:
            row = connection.execute(
                """
                INSERT INTO web_document_governance (document_id, created_by)
                SELECT id, %s FROM documents
                WHERE id = %s AND canonical_url IS NOT NULL
                ON CONFLICT (document_id) DO UPDATE
                SET last_fetched_at = now(),
                    next_review_at = now() +
                        make_interval(days => web_document_governance.refresh_interval_days),
                    last_refresh_error = NULL,
                    updated_at = now()
                RETURNING *
                """,
                (created_by, document_id),
            ).fetchone()
            connection.commit()
        if not row:
            raise ValueError("Web governance can only be registered for an imported web page.")
        return dict(row)

    def list_records(
        self,
        *,
        lifecycle_status: str | None = None,
        due_only: bool = False,
    ) -> list[dict]:
        clauses: list[str] = []
        values: list[object] = []
        if lifecycle_status:
            clauses.append("g.lifecycle_status = %s")
            values.append(lifecycle_status)
        if due_only:
            clauses.append("g.next_review_at <= now()")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT g.*, d.canonical_url, d.source_url, d.status AS document_status,
                    COALESCE(m.title, d.original_filename) AS title
                FROM web_document_governance g
                JOIN documents d ON d.id = g.document_id
                LEFT JOIN document_metadata m ON m.document_id = d.id
                {where_sql}
                ORDER BY g.next_review_at ASC, g.document_id
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def update(
        self,
        document_id: str,
        *,
        lifecycle_status: str | None = None,
        refresh_interval_days: int | None = None,
        next_review_at: datetime | None = None,
    ) -> dict:
        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE web_document_governance
                SET lifecycle_status = COALESCE(%s, lifecycle_status),
                    refresh_interval_days = COALESCE(%s, refresh_interval_days),
                    next_review_at = COALESCE(
                        %s,
                        CASE WHEN %s IS NOT NULL
                            THEN now() + make_interval(days => %s)
                            ELSE next_review_at
                        END
                    ),
                    updated_at = now()
                WHERE document_id = %s
                RETURNING *
                """,
                (
                    lifecycle_status,
                    refresh_interval_days,
                    next_review_at,
                    refresh_interval_days,
                    refresh_interval_days,
                    document_id,
                ),
            ).fetchone()
            if row and lifecycle_status is not None:
                # Archived pages remain for audit/history but disappear from
                # ordinary users' retrieval scope through the approved flag.
                connection.execute(
                    "UPDATE documents SET approved = %s WHERE id = %s",
                    (lifecycle_status != "archived", document_id),
                )
            connection.commit()
        if not row:
            raise FileNotFoundError("Web document governance record not found.")
        return dict(row)


web_governance_repository = WebGovernanceRepository()
