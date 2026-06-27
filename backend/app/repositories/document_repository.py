from uuid import UUID

from sqlalchemy import text

from app.core.database import database
from app.schemas.document import (
    DocumentAssetRead,
    DocumentDetailRead,
    DocumentMetadataRead,
    DocumentSearchResultRead,
    DocumentSnippetRead,
    DocumentSourceInfoRead,
    DocumentVersionRead,
)


def _preview(text_value: str, max_length: int = 500) -> str:
    normalized = " ".join(text_value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return []
        separators = ["\n", ";", ","]
        for separator in separators:
            if separator in text_value:
                return [item.strip() for item in text_value.split(separator) if item.strip()]
        return [text_value]
    return [str(value)]


class DocumentRepository:
    """Read repository for researcher-facing processed documents."""

    async def list_documents(self, limit: int = 100) -> list[DocumentSearchResultRead]:
        factory = self.session_factory()
        async with factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select
                          d.id,
                          d.original_filename,
                          d.status,
                          d.approved,
                          d.uploaded_at,
                          d.processed_at,
                          m.title,
                          m.summary,
                          m.source_organisation,
                          m.country_region,
                          m.year,
                          m.keywords
                        from public.documents d
                        left join public.document_metadata m on m.document_id = d.id
                        order by d.uploaded_at desc
                        limit :limit
                        """
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
        return [self._search_result_from_row(row, match_fields=[]) for row in rows]

    async def search_documents(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[DocumentSearchResultRead]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        factory = self.session_factory()
        async with factory() as session:
            pattern = f"%{normalized_query}%"
            rows = (
                await session.execute(
                    text(
                        """
                        select
                          d.id,
                          d.original_filename,
                          d.status,
                          d.approved,
                          d.uploaded_at,
                          d.processed_at,
                          m.title,
                          m.summary,
                          m.source_organisation,
                          m.country_region,
                          m.year,
                          m.keywords,
                          array_remove(array[
                            case when lower(d.original_filename) like :pattern
                              then 'filename' end,
                            case when lower(coalesce(m.title, '')) like :pattern
                              then 'title' end,
                            case when lower(coalesce(m.summary, '')) like :pattern
                              then 'summary' end,
                            case when lower(coalesce(m.keywords, '')) like :pattern
                              then 'keywords' end
                          ], null) as match_fields
                        from public.documents d
                        left join public.document_metadata m on m.document_id = d.id
                        where
                          lower(d.original_filename) like :pattern
                          or lower(coalesce(m.title, '')) like :pattern
                          or lower(coalesce(m.summary, '')) like :pattern
                          or lower(coalesce(m.keywords, '')) like :pattern
                        order by d.uploaded_at desc
                        limit :limit
                        """
                    ),
                    {"pattern": pattern, "limit": limit},
                )
            ).mappings().all()
        return [
            self._search_result_from_row(
                row,
                match_fields=list(row["match_fields"] or []),
            )
            for row in rows
        ]

    async def get(self, document_id: UUID) -> DocumentSearchResultRead | None:
        factory = self.session_factory()
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        select
                          d.id,
                          d.original_filename,
                          d.status,
                          d.approved,
                          d.uploaded_at,
                          d.processed_at,
                          m.title,
                          m.summary,
                          m.source_organisation,
                          m.country_region,
                          m.year,
                          m.keywords
                        from public.documents d
                        left join public.document_metadata m on m.document_id = d.id
                        where d.id = :document_id
                        """
                    ),
                    {"document_id": document_id},
                )
            ).mappings().first()
        if row is None:
            return None
        return self._search_result_from_row(row, match_fields=[])

    async def get_detail(
        self,
        document_id: UUID,
        *,
        snippet_limit: int = 8,
    ) -> DocumentDetailRead | None:
        factory = self.session_factory()
        async with factory() as session:
            document_row = (
                await session.execute(
                    text(
                        """
                        select
                          d.id,
                          d.original_filename,
                          d.stored_filename,
                          d.file_path,
                          d.file_size,
                          d.sha256,
                          d.mime_type,
                          d.status,
                          d.approved,
                          d.access_level,
                          d.uploaded_at,
                          d.processed_at,
                          d.error_message,
                          m.title,
                          m.summary,
                          m.source_type,
                          m.source_organisation,
                          m.country_region,
                          m.language,
                          m.year,
                          m.publication_date,
                          m.policy_areas,
                          m.keywords,
                          m.stakeholders,
                          m.implementation_risks,
                          m.metadata_json
                        from public.documents d
                        left join public.document_metadata m on m.document_id = d.id
                        where d.id = :document_id
                        """
                    ),
                    {"document_id": document_id},
                )
            ).mappings().first()
            if document_row is None:
                return None

            snippet_rows = (
                await session.execute(
                    text(
                        """
                        select
                          id,
                          chunk_index,
                          page_start,
                          page_end,
                          section_title,
                          language,
                          text,
                          token_count,
                          keywords,
                          metadata_json
                        from public.document_chunks
                        where document_id = :document_id
                        order by chunk_index
                        limit :snippet_limit
                        """
                    ),
                    {"document_id": document_id, "snippet_limit": snippet_limit},
                )
            ).mappings().all()
            snippet_count = (
                await session.execute(
                    text(
                        """
                        select count(*)
                        from public.document_chunks
                        where document_id = :document_id
                        """
                    ),
                    {"document_id": document_id},
                )
            ).scalar_one()
        return self._detail_from_rows(document_row, snippet_rows, snippet_count)

    async def chunks(
        self,
        document_id: UUID,
        *,
        limit: int = 20,
    ) -> list[DocumentSnippetRead] | None:
        detail = await self.get_detail(document_id, snippet_limit=limit)
        if detail is None:
            return None
        return detail.snippets

    async def versions(self, document_id: UUID) -> list[DocumentVersionRead] | None:
        if await self.get(document_id) is None:
            return None
        return []

    async def assets(self, document_id: UUID) -> list[DocumentAssetRead] | None:
        if await self.get(document_id) is None:
            return None
        return []

    @staticmethod
    def _search_result_from_row(row, *, match_fields: list[str]) -> DocumentSearchResultRead:
        return DocumentSearchResultRead(
            document_id=row["id"],
            original_filename=row["original_filename"],
            title=row["title"],
            summary=row["summary"],
            source_organisation=row["source_organisation"],
            country_region=row["country_region"],
            year=row["year"],
            keywords=_string_list(row["keywords"]),
            status=row["status"],
            approved=row["approved"],
            uploaded_at=row["uploaded_at"],
            processed_at=row["processed_at"],
            match_fields=match_fields,
        )

    @staticmethod
    def _detail_from_rows(
        document_row,
        snippet_rows,
        snippet_count: int,
    ) -> DocumentDetailRead:
        metadata_json = document_row["metadata_json"] or {}
        source_url = metadata_json.get("source_url") or metadata_json.get("url")
        metadata = DocumentMetadataRead(
            title=document_row["title"],
            summary=document_row["summary"],
            source_type=document_row["source_type"],
            source_organisation=document_row["source_organisation"],
            country_region=document_row["country_region"],
            language=document_row["language"],
            year=document_row["year"],
            publication_date=document_row["publication_date"],
            policy_areas=_string_list(document_row["policy_areas"]),
            keywords=_string_list(document_row["keywords"]),
            stakeholders=_string_list(document_row["stakeholders"]),
            implementation_risks=_string_list(document_row["implementation_risks"]),
            metadata=metadata_json,
        )
        return DocumentDetailRead(
            document_id=document_row["id"],
            status=document_row["status"],
            approved=document_row["approved"],
            uploaded_at=document_row["uploaded_at"],
            processed_at=document_row["processed_at"],
            summary=document_row["summary"],
            metadata=metadata,
            source=DocumentSourceInfoRead(
                source_type=document_row["source_type"],
                source_organisation=document_row["source_organisation"],
                source_url=source_url,
                original_filename=document_row["original_filename"],
                mime_type=document_row["mime_type"],
                file_size=document_row["file_size"],
                access_level=document_row["access_level"],
            ),
            snippets=[
                DocumentSnippetRead(
                    chunk_id=row["id"],
                    chunk_index=row["chunk_index"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    section_title=row["section_title"],
                    language=row["language"],
                    text_preview=_preview(row["text"]),
                    token_count=row["token_count"],
                    keywords=_string_list(row["keywords"]),
                    metadata=row["metadata_json"] or {},
                )
                for row in snippet_rows
            ],
            snippet_count=snippet_count,
        )

    @staticmethod
    def session_factory():
        if database.session_factory is None:
            raise RuntimeError("Database session factory is not initialized")
        return database.session_factory


document_repository = DocumentRepository()
