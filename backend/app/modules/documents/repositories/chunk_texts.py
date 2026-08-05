"""Read-only chunk text access for BM25 keyword retrieval.

Returns rows in the SAME shape the dense vector search produces (minus
`distance`), so hybrid fusion is shape-transparent to every downstream
consumer. See docs/BM25_HYBRID_RETRIEVAL.md.
"""

from __future__ import annotations

from app.core.database import get_connection

# Mirrors the visibility rule of EmbeddingRepository.retrieve_all: restricted
# or unapproved documents are only searchable for admins. Scoped queries
# (explicit document_ids) skip it — the caller already resolved those ids
# under its own access check, exactly like the scoped dense search.
_VISIBILITY_SQL = "d.approved = true AND d.access_level = 'public'"


class ChunkTextRepository:
    def corpus_fingerprint(
        self,
        document_ids: list[str] | None = None,
        *,
        include_restricted: bool = False,
    ) -> tuple[int, str | None]:
        """(chunk_count, newest created_at) for the scope — cheap change marker."""
        clauses: list[str] = []
        values: list[object] = []
        if document_ids is not None:
            clauses.append("c.document_id = ANY(%s::uuid[])")
            values.append(list(document_ids))
        elif not include_restricted:
            clauses.append(_VISIBILITY_SQL)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT count(*) AS chunk_count, max(c.created_at) AS newest
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                {where_sql}
                """,
                tuple(values),
            ).fetchone()
        if not row:
            return 0, None
        newest = row["newest"]
        return int(row["chunk_count"]), (str(newest) if newest is not None else None)

    def list_chunk_rows(
        self,
        document_ids: list[str] | None = None,
        *,
        include_restricted: bool = False,
    ) -> list[dict]:
        clauses: list[str] = []
        values: list[object] = []
        if document_ids is not None:
            clauses.append("c.document_id = ANY(%s::uuid[])")
            values.append(list(document_ids))
        elif not include_restricted:
            clauses.append(_VISIBILITY_SQL)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.id AS chunk_id, c.document_id,
                    d.original_filename AS file,
                    COALESCE(dm.title, d.original_filename) AS doc_title,
                    c.page_start, c.page_end,
                    c.text, c.token_count, c.language
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                LEFT JOIN document_metadata dm ON dm.document_id = d.id
                {where_sql}
                ORDER BY c.document_id, c.chunk_index
                """,
                tuple(values),
            ).fetchall()
        return [
            {
                **dict(row),
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "page": row["page_start"],
            }
            for row in rows
        ]


chunk_text_repository = ChunkTextRepository()
