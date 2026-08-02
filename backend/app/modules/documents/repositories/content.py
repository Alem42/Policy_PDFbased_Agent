import json
from uuid import uuid4

from app.core.database import get_connection
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.repositories.helpers import iso_value, row_to_metadata, string_list
from app.modules.documents.repositories.processing_jobs import processing_job_repository


class DocumentContentRepository:
    """Persists extracted pages, generated metadata, and document content views."""

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
        self,
        document_id: str,
        metadata: dict,
        generated_by_model: str | None,
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
                SET title = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.title IS NOT NULL
                        THEN document_metadata.title ELSE EXCLUDED.title END,
                    summary = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.summary IS NOT NULL
                        THEN document_metadata.summary ELSE EXCLUDED.summary END,
                    source_type = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.source_type IS NOT NULL
                        THEN document_metadata.source_type ELSE EXCLUDED.source_type END,
                    source_organisation = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.source_organisation IS NOT NULL
                        THEN document_metadata.source_organisation
                        ELSE EXCLUDED.source_organisation END,
                    country_region = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.country_region IS NOT NULL
                        THEN document_metadata.country_region ELSE EXCLUDED.country_region END,
                    language = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.language IS NOT NULL
                        THEN document_metadata.language ELSE EXCLUDED.language END,
                    year = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.year IS NOT NULL
                        THEN document_metadata.year ELSE EXCLUDED.year END,
                    publication_date = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND document_metadata.publication_date IS NOT NULL
                        THEN document_metadata.publication_date
                        ELSE EXCLUDED.publication_date END,
                    policy_areas = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND cardinality(document_metadata.policy_areas) > 0
                        THEN document_metadata.policy_areas ELSE EXCLUDED.policy_areas END,
                    keywords = CASE WHEN document_metadata.reviewed_at IS NOT NULL
                            AND cardinality(document_metadata.keywords) > 0
                        THEN document_metadata.keywords ELSE EXCLUDED.keywords END,
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

    def get_detail_record(self, identifier: str, *, include_restricted: bool = False) -> dict:
        document = document_repository.get_record(
            identifier,
            include_restricted=include_restricted,
        )
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
        detail = row_to_metadata(dict(row))
        detail.update(
            {
                "sha256": row["sha256"],
                "mime_type": row["mime_type"],
                "stakeholders": string_list(row.get("stakeholders")),
                "implementation_risks": string_list(row.get("implementation_risks")),
                "metadata_json": row.get("metadata_json") or {},
                "generated_by_model": row.get("generated_by_model"),
                "generated_at": iso_value(row.get("generated_at")),
                "jobs": [
                    {
                        **dict(job),
                        "started_at": iso_value(job.get("started_at")),
                        "finished_at": iso_value(job.get("finished_at")),
                        "details_json": job.get("details_json") or {},
                    }
                    for job in jobs
                ],
            }
        )
        return detail

    def list_chunk_records(
        self,
        identifier: str,
        *,
        include_restricted: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        document = document_repository.get_record(
            identifier,
            include_restricted=include_restricted,
        )
        rows = embedding_repository.list_for_document(str(document["id"]), limit)
        return [
            {
                **dict(row),
                "id": str(row["id"]),
                "chunk_id": str(row["id"]),
                "document_id": str(document["id"]),
                "created_at": iso_value(row.get("created_at")),
                "keywords": string_list(row.get("keywords")),
                "metadata_json": row.get("metadata_json") or {},
                "text_preview": row["text"][:500],
            }
            for row in rows
        ]

    def get_pages(self, identifier: str, *, include_restricted: bool = False) -> list[dict]:
        document = document_repository.get_record(
            identifier,
            include_restricted=include_restricted,
        )
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT page_number, text FROM document_pages
                WHERE document_id = %s ORDER BY page_number
                """,
                (document["id"],),
            ).fetchall()
        display_name = document.get("title") or document["original_filename"]
        return [
            {
                "file": document["original_filename"],
                "title": display_name,
                "page": row["page_number"],
                "text": row["text"],
            }
            for row in rows
        ]

    def update_metadata(self, identifier: str, payload: dict) -> dict:
        """Partial metadata update, shared by the admin edit dialog and the
        optional metadata form fields on upload. Accepts both the current
        column-matching keys (country_region, year, policy_areas, keywords,
        ...) and the legacy upload-form keys (country_or_region,
        published_year, policy_area singular, tags, ...) for compatibility.
        """
        document = document_repository.get_record(identifier)

        country_region = payload.get("country_region") or payload.get("country_or_region")
        year = payload.get("year")
        if year is None:
            year = payload.get("published_year")
        policy_areas = payload.get("policy_areas")
        if policy_areas is None and payload.get("policy_area"):
            policy_areas = [payload["policy_area"]]
        keywords = payload.get("keywords")
        if keywords is None:
            keywords = payload.get("tags")

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO document_metadata (
                    document_id, title, summary, source_type, source_organisation,
                    country_region, language, year, publication_date,
                    policy_areas, keywords, reviewed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::text[], '{}'), COALESCE(%s::text[], '{}'), now())
                ON CONFLICT (document_id) DO UPDATE
                SET title = COALESCE(EXCLUDED.title, document_metadata.title),
                    summary = COALESCE(EXCLUDED.summary, document_metadata.summary),
                    source_type = COALESCE(EXCLUDED.source_type, document_metadata.source_type),
                    source_organisation = COALESCE(
                        EXCLUDED.source_organisation, document_metadata.source_organisation
                    ),
                    country_region = COALESCE(
                        EXCLUDED.country_region, document_metadata.country_region
                    ),
                    language = COALESCE(EXCLUDED.language, document_metadata.language),
                    year = COALESCE(EXCLUDED.year, document_metadata.year),
                    publication_date = COALESCE(
                        EXCLUDED.publication_date, document_metadata.publication_date
                    ),
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
                    payload.get("source_type"),
                    payload.get("source_organisation"),
                    country_region,
                    payload.get("language"),
                    year,
                    payload.get("publication_date"),
                    policy_areas,
                    keywords,
                ),
            )
            connection.commit()
        if payload.get("approved") is not None or payload.get("access_level") is not None:
            document_repository.update_governance(
                str(document["id"]),
                approved=payload.get("approved"),
                access_level=payload.get("access_level"),
            )
        return self.get_detail_record(str(document["id"]), include_restricted=True)


document_content_repository = DocumentContentRepository()
