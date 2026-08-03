from psycopg.errors import UniqueViolation

from app.core.database import get_connection
from app.modules.documents.exceptions import DuplicateDocumentError
from app.modules.documents.repositories.helpers import looks_like_uuid


class DocumentRepository:
    """Persists document identity, visibility, status, and file metadata."""

    def find_by_checksum(self, checksum: str) -> dict | None:
        """Return the existing document with this SHA-256, or None (L1 dedup)."""
        with get_connection() as connection:
            row = connection.execute(
                "SELECT id, original_filename FROM documents WHERE sha256 = %s LIMIT 1",
                (checksum,),
            ).fetchone()
        return dict(row) if row else None

    def find_by_content_hash(
        self, content_hash: str, *, exclude_id: str | None = None
    ) -> dict | None:
        """Return an existing document with this normalised-text hash (L2 dedup)."""
        exclude_sql = "AND id != %s" if exclude_id else ""
        values = (content_hash, exclude_id) if exclude_id else (content_hash,)
        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT id, original_filename FROM documents
                WHERE content_hash = %s {exclude_sql}
                LIMIT 1
                """,
                values,
            ).fetchone()
        return dict(row) if row else None

    def find_by_source_url(self, source_url: str) -> dict | None:
        """Return the document owning this canonical URL, or a legacy match."""
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, original_filename FROM documents
                WHERE canonical_url = %s OR (canonical_url IS NULL AND source_url = %s)
                ORDER BY (canonical_url = %s) DESC, uploaded_at ASC
                LIMIT 1
                """,
                (source_url, source_url, source_url),
            ).fetchone()
        return dict(row) if row else None

    def set_content_hash(self, document_id: str, content_hash: str) -> None:
        with get_connection() as connection:
            connection.execute(
                "UPDATE documents SET content_hash = %s WHERE id = %s",
                (content_hash, document_id),
            )
            connection.commit()

    def create(
        self,
        *,
        document_id: str,
        original_filename: str,
        stored_filename: str,
        file_path: str,
        content: bytes,
        checksum: str,
        mime_type: str = "application/pdf",
        upsert: bool = False,
        source_url: str | None = None,
        canonical_url: str | None = None,
        imported_by: str | None = None,
        imported_via: str | None = None,
    ) -> str:
        conflict_sql = (
            """
            ON CONFLICT (file_path) DO UPDATE
            SET original_filename = EXCLUDED.original_filename,
                stored_filename = EXCLUDED.stored_filename,
                file_size = EXCLUDED.file_size,
                sha256 = EXCLUDED.sha256,
                mime_type = EXCLUDED.mime_type
        """
            if upsert
            else ""
        )
        try:
            with get_connection() as connection:
                row = connection.execute(
                    f"""
                    INSERT INTO documents (
                        id, original_filename, stored_filename, file_path,
                        file_size, sha256, mime_type, status,
                        source_url, canonical_url, imported_by, imported_via
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'uploaded', %s, %s, %s, %s)
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
                        mime_type,
                        source_url,
                        canonical_url,
                        imported_by,
                        imported_via,
                    ),
                ).fetchone()
                connection.commit()
        except UniqueViolation as exc:
            # Backstop for the L1 pre-check racing with a concurrent identical
            # upload (or a same-content file under a different path): the
            # sha256 UNIQUE constraint serialises it here.
            if getattr(exc.diag, "constraint_name", "") == "documents_sha256_key":
                existing = self.find_by_checksum(checksum)
                if existing:
                    raise DuplicateDocumentError(
                        str(existing["id"]), existing["original_filename"]
                    ) from exc
            if getattr(exc.diag, "constraint_name", "") == "uq_documents_canonical_url":
                existing = self.find_by_source_url(canonical_url or source_url or "")
                if existing:
                    raise DuplicateDocumentError(
                        str(existing["id"]), existing["original_filename"]
                    ) from exc
            raise
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
        status: str | None = None,
        source_type: str | None = None,
        sort: str = "uploaded_desc",
        offset: int = 0,
        limit: int | None = None,
    ) -> list[dict]:
        clauses, values = self._filters(
            include_restricted=include_restricted,
            policy_area=policy_area,
            country_or_region=country_or_region,
            source_organisation=source_organisation,
            tag=tag,
            query=query,
            status=status,
            source_type=source_type,
        )
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = "LIMIT %s" if limit is not None else ""
        offset_sql = "OFFSET %s" if offset else ""
        if limit is not None:
            values.append(limit)
        if offset:
            values.append(offset)
        order_sql = {
            "uploaded_desc": "d.uploaded_at DESC, d.original_filename ASC",
            "name_asc": "d.original_filename ASC, d.uploaded_at DESC",
            "year_desc": "m.year DESC NULLS LAST, d.uploaded_at DESC",
            "chunks_desc": "chunk_count DESC, d.uploaded_at DESC",
        }.get(sort, "d.uploaded_at DESC, d.original_filename ASC")
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
                ORDER BY {order_sql}
                {limit_sql}
                {offset_sql}
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_records(
        self,
        *,
        include_restricted: bool = False,
        policy_area: str | None = None,
        country_or_region: str | None = None,
        source_organisation: str | None = None,
        tag: str | None = None,
        query: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> int:
        clauses, values = self._filters(
            include_restricted=include_restricted,
            policy_area=policy_area,
            country_or_region=country_or_region,
            source_organisation=source_organisation,
            tag=tag,
            query=query,
            status=status,
            source_type=source_type,
        )
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT count(*) AS total
                FROM documents d
                LEFT JOIN document_metadata m ON m.document_id = d.id
                {where_sql}
                """,
                tuple(values),
            ).fetchone()
        return int(row["total"])

    @staticmethod
    def _filters(
        *,
        include_restricted: bool,
        policy_area: str | None,
        country_or_region: str | None,
        source_organisation: str | None,
        tag: str | None,
        query: str | None,
        status: str | None,
        source_type: str | None,
    ) -> tuple[list[str], list[object]]:
        clauses: list[str] = []
        values: list[object] = []
        if not include_restricted:
            clauses.append("d.approved = true AND d.access_level = 'public'")
        for value, clause in (
            (policy_area, "%s = ANY(m.policy_areas)"),
            (country_or_region, "m.country_region = %s"),
            (source_organisation, "m.source_organisation = %s"),
            (tag, "%s = ANY(m.keywords)"),
            (status, "d.status = %s"),
            (source_type, "m.source_type = %s"),
        ):
            if value:
                clauses.append(clause)
                values.append(value)
        clean_query = query.strip() if query else ""
        if clean_query:
            clauses.append(
                """(
                    d.original_filename ILIKE %s ESCAPE '!' OR
                    m.title ILIKE %s ESCAPE '!' OR
                    m.summary ILIKE %s ESCAPE '!' OR
                    m.country_region ILIKE %s ESCAPE '!' OR
                    m.source_type ILIKE %s ESCAPE '!' OR
                    m.source_organisation ILIKE %s ESCAPE '!' OR
                    array_to_string(m.policy_areas, ' ') ILIKE %s ESCAPE '!' OR
                    array_to_string(m.keywords, ' ') ILIKE %s ESCAPE '!' OR
                    CAST(m.year AS TEXT) ILIKE %s ESCAPE '!'
                )"""
            )
            escaped_query = clean_query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            pattern = f"%{escaped_query}%"
            values.extend([pattern] * 9)
        return clauses, values

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
