"""Read-only metadata projection used by conservative chat filtering."""

from __future__ import annotations

from app.core.database import get_connection


class MetadataFilterRepository:
    def list_records(
        self,
        document_ids: list[str] | None = None,
        *,
        include_restricted: bool = False,
    ) -> list[dict]:
        clauses: list[str] = []
        values: list[object] = []
        if document_ids is not None:
            if not document_ids:
                return []
            clauses.append("d.id = ANY(%s::uuid[])")
            values.append(document_ids)
        if not include_restricted:
            clauses.append("d.approved = true AND d.access_level = 'public'")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT d.id, m.policy_areas, m.country_region,
                    m.source_organisation, m.language, m.keywords, m.year
                FROM documents d
                LEFT JOIN document_metadata m ON m.document_id = d.id
                {where_sql}
                ORDER BY d.uploaded_at DESC
                """,
                tuple(values),
            ).fetchall()
        return [
            {
                **dict(row),
                "id": str(row["id"]),
                "policy_areas": list(row.get("policy_areas") or []),
                "keywords": list(row.get("keywords") or []),
            }
            for row in rows
        ]


metadata_filter_repository = MetadataFilterRepository()
