from uuid import uuid4

from app.core.database import get_connection


class EmbeddingRepository:
    """Persistence and similarity search for document chunks and embeddings."""

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[dict],
        embeddings: list[str],
        *,
        language: str | None,
        embedding_model: str,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Each chunk must have exactly one embedding.")
        with get_connection() as connection:
            connection.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, chunk_index, page_start, page_end,
                        section_title, language, text, token_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk_id,
                        document_id,
                        chunk["chunk_index"],
                        chunk["page_start"],
                        chunk["page_end"],
                        chunk["section_title"],
                        language,
                        chunk["text"],
                        chunk["token_count"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding, embedding_model)
                    VALUES (%s, %s::vector, %s)
                    """,
                    (chunk_id, embedding, embedding_model),
                )
            connection.commit()

    def list_for_document(self, document_id: str, limit: int | None = None) -> list[dict]:
        limit_sql = "LIMIT %s" if limit is not None else ""
        values: list[object] = [document_id]
        if limit is not None:
            values.append(limit)
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, e.embedding_model
                FROM document_chunks c
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id
                WHERE c.document_id = %s ORDER BY c.chunk_index {limit_sql}
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def retrieve(self, query_vector: str, document_ids: list[str], *, limit: int) -> list[dict]:
        if not document_ids:
            return []
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT c.id AS chunk_id, c.document_id,
                    d.original_filename AS file,
                    COALESCE(dm.title, d.original_filename) AS doc_title,
                    c.page_start, c.page_end,
                    c.text, c.token_count, c.language,
                    e.embedding <=> %s::vector AS distance
                FROM chunk_embeddings e
                JOIN document_chunks c ON c.id = e.chunk_id
                JOIN documents d ON d.id = c.document_id
                LEFT JOIN document_metadata dm ON dm.document_id = d.id
                WHERE c.document_id = ANY(%s::uuid[])
                ORDER BY e.embedding <=> %s::vector LIMIT %s
                """,
                (query_vector, document_ids, query_vector, limit),
            ).fetchall()
        return [
            {
                **dict(row),
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "page": row["page_start"],
                "distance": float(row["distance"]),
            }
            for row in rows
        ]


embedding_repository = EmbeddingRepository()
