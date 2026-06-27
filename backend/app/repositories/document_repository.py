from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from app.core.database import get_connection
from app.repositories.embedding_repository import embedding_repository
from app.repositories.processing_job_repository import processing_job_repository
from app.schemas.document import (
    DocumentAssetRead,
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentMetadataRead,
    DocumentSearchResultRead,
    DocumentSourceInfoRead,
    DocumentVersionRead,
)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        for separator in ("\n", ";", ","):
            if separator in value:
                return [item.strip() for item in value.split(separator) if item.strip()]
        return [value.strip()] if value.strip() else []
    return [str(value)]


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


class DocumentRepository:
    """Single persistence boundary for uploaded and processed PDF documents."""

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

    def set_status(self, document_id: str, status: str, error_message: str | None = None) -> None:
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

    def replace_pages(self, document_id: str, pages: list[dict]) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM document_pages WHERE document_id = %s", (document_id,))
            for page in pages:
                text = page["text"]
                connection.execute(
                    """
                    INSERT INTO document_pages (id, document_id, page_number, text, char_count)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (str(uuid4()), document_id, page["page"], text, len(text)),
                )
            connection.commit()

    def upsert_generated_metadata(
        self, document_id: str, metadata: dict, generated_by_model: str | None
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO document_metadata (
                    document_id, title, summary, source_type, source_organisation,
                    country_region, language, year, publication_date, policy_areas,
                    keywords, stakeholders, implementation_risks, metadata_json,
                    generated_by_model, generated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, now()
                )
                ON CONFLICT (document_id) DO UPDATE
                SET title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    source_type = EXCLUDED.source_type,
                    source_organisation = EXCLUDED.source_organisation,
                    country_region = EXCLUDED.country_region,
                    language = EXCLUDED.language,
                    year = EXCLUDED.year,
                    publication_date = EXCLUDED.publication_date,
                    policy_areas = EXCLUDED.policy_areas,
                    keywords = EXCLUDED.keywords,
                    stakeholders = EXCLUDED.stakeholders,
                    implementation_risks = EXCLUDED.implementation_risks,
                    metadata_json = EXCLUDED.metadata_json,
                    generated_by_model = EXCLUDED.generated_by_model,
                    generated_at = now()
                """,
                (
                    document_id,
                    metadata.get("title"),
                    metadata.get("summary"),
                    metadata.get("source_type"),
                    metadata.get("source_organisation"),
                    metadata.get("country_region"),
                    metadata.get("language"),
                    metadata.get("year"),
                    metadata.get("publication_date"),
                    metadata.get("policy_areas", []),
                    metadata.get("keywords", []),
                    metadata.get("stakeholders", []),
                    metadata.get("implementation_risks", []),
                    json.dumps(metadata.get("metadata_json", {})),
                    generated_by_model,
                ),
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
            if _looks_like_uuid(identifier):
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

    def get_detail_record(self, identifier: str, *, include_restricted: bool = False) -> dict:
        document = self.get_record(identifier, include_restricted=include_restricted)
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT d.*, m.title, m.summary, m.source_type,
                    m.source_organisation, m.country_region, m.language,
                    m.publication_date, m.year, m.policy_areas, m.keywords,
                    m.stakeholders, m.implementation_risks, m.metadata_json,
                    m.generated_by_model, m.generated_at,
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
                WHERE d.id = %s
                """,
                (document["id"],),
            ).fetchone()
        jobs = processing_job_repository.list_for_document(str(document["id"]))
        detail = self.to_metadata(dict(row))
        detail.update(
            {
                "sha256": row["sha256"],
                "mime_type": row["mime_type"],
                "stakeholders": _string_list(row.get("stakeholders")),
                "implementation_risks": _string_list(row.get("implementation_risks")),
                "metadata_json": row.get("metadata_json") or {},
                "generated_by_model": row.get("generated_by_model"),
                "generated_at": self._iso(row.get("generated_at")),
                "jobs": [
                    {
                        **dict(job),
                        "started_at": self._iso(job.get("started_at")),
                        "finished_at": self._iso(job.get("finished_at")),
                        "details_json": job.get("details_json") or {},
                    }
                    for job in jobs
                ],
            }
        )
        return detail

    def list_chunk_records(
        self, identifier: str, *, include_restricted: bool = False, limit: int | None = None
    ) -> list[dict]:
        document = self.get_record(identifier, include_restricted=include_restricted)
        rows = embedding_repository.list_for_document(str(document["id"]), limit)
        return [
            {
                **dict(row),
                "id": str(row["id"]),
                "chunk_id": str(row["id"]),
                "document_id": str(document["id"]),
                "created_at": self._iso(row.get("created_at")),
                "keywords": _string_list(row.get("keywords")),
                "metadata_json": row.get("metadata_json") or {},
                "text_preview": row["text"][:500],
            }
            for row in rows
        ]

    def get_pages(self, identifier: str, *, include_restricted: bool = False) -> list[dict]:
        document = self.get_record(identifier, include_restricted=include_restricted)
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT page_number, text FROM document_pages
                WHERE document_id = %s ORDER BY page_number
                """,
                (document["id"],),
            ).fetchall()
        return [
            {"file": document["original_filename"], "page": row["page_number"], "text": row["text"]}
            for row in rows
        ]

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
        return self.get_detail_record(str(document["id"]), include_restricted=True)

    def update_metadata(self, identifier: str, payload: dict) -> dict:
        document = self.get_record(identifier)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO document_metadata (
                    document_id, title, summary, source_organisation,
                    country_region, year, policy_areas, keywords
                )
                VALUES (%s, %s, %s, %s, %s, %s,
                    COALESCE(%s::text[], '{}'), COALESCE(%s::text[], '{}'))
                ON CONFLICT (document_id) DO UPDATE
                SET title = COALESCE(EXCLUDED.title, document_metadata.title),
                    summary = COALESCE(EXCLUDED.summary, document_metadata.summary),
                    source_organisation = COALESCE(
                        EXCLUDED.source_organisation, document_metadata.source_organisation
                    ),
                    country_region = COALESCE(
                        EXCLUDED.country_region, document_metadata.country_region
                    ),
                    year = COALESCE(EXCLUDED.year, document_metadata.year),
                    policy_areas = CASE WHEN EXCLUDED.policy_areas = '{}'
                        THEN document_metadata.policy_areas ELSE EXCLUDED.policy_areas END,
                    keywords = CASE WHEN EXCLUDED.keywords = '{}'
                        THEN document_metadata.keywords ELSE EXCLUDED.keywords END,
                    reviewed_at = now()
                """,
                (
                    document["id"],
                    payload.get("title"),
                    payload.get("summary"),
                    payload.get("source_organisation"),
                    payload.get("country_or_region"),
                    payload.get("published_year"),
                    [payload["policy_area"]] if payload.get("policy_area") else None,
                    payload.get("tags"),
                ),
            )
            connection.commit()
        if payload.get("approved") is not None or payload.get("access_level") is not None:
            return self.update_governance(
                str(document["id"]),
                approved=payload.get("approved"),
                access_level=payload.get("access_level"),
            )
        return self.get_detail_record(str(document["id"]), include_restricted=True)

    @staticmethod
    def to_metadata(row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "document_id": str(row["id"]),
            "name": row["original_filename"],
            "original_filename": row["original_filename"],
            "stored_filename": row["stored_filename"],
            "relative_path": row["file_path"],
            "file_path": row["file_path"],
            "size": row["file_size"],
            "file_size": row["file_size"],
            "modified_at": row["uploaded_at"].timestamp(),
            "status": row["status"],
            "approved": row.get("approved", True),
            "access_level": row.get("access_level", "public"),
            "uploaded_at": DocumentRepository._iso(row.get("uploaded_at")),
            "processed_at": DocumentRepository._iso(row.get("processed_at")),
            "error_message": row.get("error_message"),
            "title": row.get("title"),
            "summary": row.get("summary"),
            "source_type": row.get("source_type"),
            "source_organisation": row.get("source_organisation"),
            "country_region": row.get("country_region"),
            "language": row.get("language"),
            "publication_date": DocumentRepository._iso(row.get("publication_date")),
            "keywords": _string_list(row.get("keywords")),
            "policy_areas": _string_list(row.get("policy_areas")),
            "year": row.get("year"),
            "page_count": row.get("page_count") or 0,
            "chunk_count": row.get("chunk_count") or 0,
        }

    async def list_documents(self, limit: int = 100) -> list[DocumentSearchResultRead]:
        rows = await asyncio.to_thread(self.list_records, limit=limit)
        return [self._search_result(row) for row in rows]

    async def search_documents(
        self, query: str, *, limit: int = 20
    ) -> list[DocumentSearchResultRead]:
        rows = await asyncio.to_thread(self.list_records, query=query, limit=limit)
        return [self._search_result(row, query=query) for row in rows]

    async def get(self, document_id: UUID) -> DocumentSearchResultRead | None:
        try:
            row = await asyncio.to_thread(
                self.get_detail_record, str(document_id), include_restricted=False
            )
        except FileNotFoundError:
            return None
        return self._search_result(row)

    async def get_detail(self, document_id: UUID) -> DocumentDetailRead | None:
        try:
            detail = await asyncio.to_thread(
                self.get_detail_record, str(document_id), include_restricted=False
            )
        except FileNotFoundError:
            return None
        return self._detail_schema(detail)

    async def chunks(self, document_id: UUID, *, limit: int = 20) -> list[DocumentChunkRead] | None:
        try:
            rows = await asyncio.to_thread(
                self.list_chunk_records,
                str(document_id),
                include_restricted=False,
                limit=limit,
            )
        except FileNotFoundError:
            return None
        return [self._chunk_schema(row) for row in rows]

    async def versions(self, document_id: UUID) -> list[DocumentVersionRead] | None:
        return [] if await self.get(document_id) is not None else None

    async def assets(self, document_id: UUID) -> list[DocumentAssetRead] | None:
        return [] if await self.get(document_id) is not None else None

    def _search_result(self, row: dict, query: str | None = None) -> DocumentSearchResultRead:
        metadata = self.to_metadata(row) if "name" not in row else row
        match_fields: list[str] = []
        if query:
            lowered = query.lower()
            for field in ("original_filename", "title", "summary", "keywords"):
                if lowered in str(metadata.get(field) or "").lower():
                    match_fields.append(field)
        return DocumentSearchResultRead(
            document_id=metadata["document_id"],
            original_filename=metadata["original_filename"],
            title=metadata.get("title"),
            summary=metadata.get("summary"),
            source_organisation=metadata.get("source_organisation"),
            country_region=metadata.get("country_region"),
            year=metadata.get("year"),
            keywords=metadata.get("keywords", []),
            status=metadata["status"],
            approved=metadata.get("approved"),
            uploaded_at=metadata.get("uploaded_at"),
            processed_at=metadata.get("processed_at"),
            match_fields=match_fields,
        )

    def _detail_schema(self, detail: dict) -> DocumentDetailRead:
        return DocumentDetailRead(
            document_id=detail["document_id"],
            status=detail["status"],
            approved=detail.get("approved"),
            uploaded_at=detail.get("uploaded_at"),
            processed_at=detail.get("processed_at"),
            summary=detail.get("summary"),
            metadata=DocumentMetadataRead(
                title=detail.get("title"),
                summary=detail.get("summary"),
                source_type=detail.get("source_type"),
                source_organisation=detail.get("source_organisation"),
                country_region=detail.get("country_region"),
                language=detail.get("language"),
                year=detail.get("year"),
                publication_date=detail.get("publication_date"),
                policy_areas=detail.get("policy_areas", []),
                keywords=detail.get("keywords", []),
                stakeholders=detail.get("stakeholders", []),
                implementation_risks=detail.get("implementation_risks", []),
                metadata=detail.get("metadata_json", {}),
            ),
            source=DocumentSourceInfoRead(
                source_type=detail.get("source_type"),
                source_organisation=detail.get("source_organisation"),
                source_url=detail.get("metadata_json", {}).get("source_url"),
                original_filename=detail.get("original_filename"),
                mime_type=detail.get("mime_type"),
                file_size=detail.get("file_size"),
                access_level=detail.get("access_level"),
            ),
            page_count=detail.get("page_count", 0),
            chunk_count=detail.get("chunk_count", 0),
        )

    @staticmethod
    def _chunk_schema(row: dict) -> DocumentChunkRead:
        return DocumentChunkRead(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            page_start=row.get("page_start"),
            page_end=row.get("page_end"),
            section_title=row.get("section_title"),
            language=row.get("language"),
            text=row["text"],
            token_count=row.get("token_count"),
            keywords=row.get("keywords", []),
            metadata=row.get("metadata_json", {}),
            created_at=row.get("created_at"),
            embedding_model=row.get("embedding_model"),
        )

    @staticmethod
    def _iso(value: object) -> str | None:
        if value is None:
            return None
        isoformat = getattr(value, "isoformat", None)
        return isoformat() if callable(isoformat) else str(value)


document_repository = DocumentRepository()
