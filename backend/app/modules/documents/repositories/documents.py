from app.core.database import get_connection
from app.modules.documents.repositories.helpers import looks_like_uuid


class DocumentRepository:
    """Persists document identity, visibility, status, and file metadata."""

    def create(
        self,
        *,
        document_id: str,
        original_filename: str,
        stored_filename: str,
        file_path: str,
        content: bytes,
        checksum: str,
        upsert: bool = False,
    ) -> str:
        conflict_sql = (
            """
            ON CONFLICT (file_path) DO UPDATE
            SET original_filename = EXCLUDED.original_filename,
                stored_filename = EXCLUDED.stored_filename,
                file_size = EXCLUDED.file_size,
                sha256 = EXCLUDED.sha256
        """
            if upsert
            else ""
        )
        with get_connection() as connection:
            row = connection.execute(
                f"""
                INSERT INTO documents (
                    id, original_filename, stored_filename, file_path,
                    file_size, sha256, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'uploaded')
                {conflict_sql}
                RETURNING id
                """,
                (
                    document_id,
                    original_filename,
                    stored_filename,
                    file_path,
                    len(content),
                    checksum,
                ),
            ).fetchone()
            connection.commit()
        return str(row["id"])

    def set_status(
        self,
        document_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        processed_sql = ", processed_at = now()" if status == "ready" else ""
        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE documents
                SET status = %s, error_message = %s {processed_sql}
                WHERE id = %s
                """,
                (status, error_message, document_id),
            )
            connection.commit()

    def known_file_paths(self) -> set[str]:
        with get_connection() as connection:
            rows = connection.execute("SELECT file_path FROM documents").fetchall()
        return {row["file_path"] for row in rows}

    def all_document_ids(self) -> list[str]:
        with get_connection() as connection:
            rows = connection.execute("SELECT id FROM documents ORDER BY uploaded_at").fetchall()
        return [str(row["id"]) for row in rows]

    def list_records(
        self,
        *,
        include_restricted: bool = False,
        policy_area: str | None = None,
        country_or_region: str | None = None,
        source_organisation: str | None = None,
        tag: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        values: list[object] = []
        if not include_restricted:
            clauses.append("d.approved = true AND d.access_level = 'public'")
        for value, clause in (
            (policy_area, "%s = ANY(m.policy_areas)"),
            (country_or_region, "m.country_region = %s"),
            (source_organisation, "m.source_organisation = %s"),
            (tag, "%s = ANY(m.keywords)"),
        ):
            if value:
                clauses.append(clause)
                values.append(value)
        if query:
            clauses.append(
                """(
                    d.original_filename ILIKE %s OR m.title ILIKE %s OR
                    m.summary ILIKE %s OR array_to_string(m.keywords, ' ') ILIKE %s
                )"""
            )
            pattern = f"%{query.strip()}%"
            values.extend([pattern] * 4)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = "LIMIT %s" if limit is not None else ""
        if limit is not None:
            values.append(limit)
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT d.*, m.title, m.summary, m.source_type,
                    m.source_organisation, m.country_region, m.language,
                    m.publication_date, m.keywords, m.policy_areas, m.year,
                    COALESCE(p.page_count, 0) AS page_count,
                    COALESCE(c.chunk_count, 0) AS chunk_count
                FROM documents d
                LEFT JOIN document_metadata m ON m.document_id = d.id
                LEFT JOIN (
                    SELECT document_id, count(*) AS page_count
                    FROM document_pages GROUP BY document_id
                ) p ON p.document_id = d.id
                LEFT JOIN (
                    SELECT document_id, count(*) AS chunk_count
                    FROM document_chunks GROUP BY document_id
                ) c ON c.document_id = d.id
                {where_sql}
                ORDER BY d.uploaded_at DESC, d.original_filename ASC
                {limit_sql}
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_record(self, identifier: str, *, include_restricted: bool = True) -> dict:
        visibility_sql = (
            "" if include_restricted else "AND approved = true AND access_level = 'public'"
        )
        with get_connection() as connection:
            if looks_like_uuid(identifier):
                row = connection.execute(
                    f"SELECT * FROM documents WHERE id = %s {visibility_sql}",
                    (identifier,),
                ).fetchone()
            else:
                row = connection.execute(
                    f"""
                    SELECT * FROM documents
                    WHERE (original_filename = %s OR stored_filename = %s OR file_path = %s)
                    {visibility_sql}
                    ORDER BY uploaded_at DESC LIMIT 1
                    """,
                    (identifier, identifier, identifier),
                ).fetchone()
        if not row:
            raise FileNotFoundError(f"PDF not found: {identifier}")
        return dict(row)

    def delete(self, identifier: str) -> dict:
        document = self.get_record(identifier)
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document["id"],))
            connection.commit()
        return document

    def update_governance(
        self,
        identifier: str,
        *,
        approved: bool | None = None,
        access_level: str | None = None,
    ) -> dict:
        if access_level is not None and access_level not in {"public", "private"}:
            raise ValueError("access_level must be public or private.")
        document = self.get_record(identifier)
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE documents SET approved = COALESCE(%s, approved),
                    access_level = COALESCE(%s, access_level)
                WHERE id = %s
                """,
                (approved, access_level, document["id"]),
            )
            connection.commit()
        return self.get_record(str(document["id"]), include_restricted=True)


document_repository = DocumentRepository()
