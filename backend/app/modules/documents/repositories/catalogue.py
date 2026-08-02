import asyncio
import math
from uuid import UUID

from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.helpers import row_to_metadata
from app.modules.documents.schemas import (
    DocumentAssetRead,
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentMetadataRead,
    DocumentSearchPageRead,
    DocumentSearchResultRead,
    DocumentSourceInfoRead,
    DocumentVersionRead,
)


class DocumentCatalogueRepository:
    """Maps persistence records into the document catalogue's API schemas."""

    async def list_documents(
        self,
        limit: int = 100,
        *,
        include_restricted: bool = False,
    ) -> list[DocumentSearchResultRead]:
        rows = await asyncio.to_thread(
            document_repository.list_records,
            limit=limit,
            include_restricted=include_restricted,
        )
        return [self._search_result(row) for row in rows]

    async def search_documents(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        policy_area: str | None = None,
        country_region: str | None = None,
        source_type: str | None = None,
        sort: str = "uploaded_desc",
        include_restricted: bool = False,
    ) -> DocumentSearchPageRead:
        filters = {
            "query": query,
            "status": status,
            "policy_area": policy_area,
            "country_or_region": country_region,
            "source_type": source_type,
            "include_restricted": include_restricted,
        }
        rows, total = await asyncio.gather(
            asyncio.to_thread(
                document_repository.list_records,
                **filters,
                sort=sort,
                offset=(page - 1) * page_size,
                limit=page_size,
            ),
            asyncio.to_thread(document_repository.count_records, **filters),
        )
        return DocumentSearchPageRead(
            items=[self._search_result(row, query=query) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size),
        )

    async def get(
        self,
        document_id: UUID,
        *,
        include_restricted: bool = False,
    ) -> DocumentSearchResultRead | None:
        try:
            row = await asyncio.to_thread(
                document_content_repository.get_detail_record,
                str(document_id),
                include_restricted=include_restricted,
            )
        except FileNotFoundError:
            return None
        return self._search_result(row)

    async def get_detail(
        self,
        document_id: UUID,
        *,
        include_restricted: bool = False,
    ) -> DocumentDetailRead | None:
        try:
            detail = await asyncio.to_thread(
                document_content_repository.get_detail_record,
                str(document_id),
                include_restricted=include_restricted,
            )
        except FileNotFoundError:
            return None
        return self._detail_schema(detail)

    async def chunks(
        self,
        document_id: UUID,
        *,
        limit: int = 20,
        include_restricted: bool = False,
    ) -> list[DocumentChunkRead] | None:
        try:
            rows = await asyncio.to_thread(
                document_content_repository.list_chunk_records,
                str(document_id),
                include_restricted=include_restricted,
                limit=limit,
            )
        except FileNotFoundError:
            return None
        return [self._chunk_schema(row) for row in rows]

    async def versions(
        self,
        document_id: UUID,
        *,
        include_restricted: bool = False,
    ) -> list[DocumentVersionRead] | None:
        return (
            []
            if await self.get(document_id, include_restricted=include_restricted) is not None
            else None
        )

    async def assets(
        self,
        document_id: UUID,
        *,
        include_restricted: bool = False,
    ) -> list[DocumentAssetRead] | None:
        return (
            []
            if await self.get(document_id, include_restricted=include_restricted) is not None
            else None
        )

    @staticmethod
    def _search_result(row: dict, query: str | None = None) -> DocumentSearchResultRead:
        metadata = row_to_metadata(row) if "name" not in row else row
        match_fields: list[str] = []
        clean_query = query.strip().lower() if query else ""
        if clean_query:
            for field in (
                "original_filename",
                "title",
                "summary",
                "country_region",
                "source_type",
                "source_organisation",
                "policy_areas",
                "keywords",
                "year",
            ):
                if clean_query in str(metadata.get(field) or "").lower():
                    match_fields.append(field)
        return DocumentSearchResultRead(
            id=metadata["id"],
            original_filename=metadata["original_filename"],
            title=metadata.get("title"),
            summary=metadata.get("summary"),
            source_type=metadata.get("source_type"),
            source_organisation=metadata.get("source_organisation"),
            country_region=metadata.get("country_region"),
            language=metadata.get("language"),
            year=metadata.get("year"),
            publication_date=metadata.get("publication_date"),
            policy_areas=metadata.get("policy_areas", []),
            keywords=metadata.get("keywords", []),
            mime_type=metadata.get("mime_type"),
            file_size=metadata.get("file_size"),
            page_count=metadata.get("page_count", 0),
            chunk_count=metadata.get("chunk_count", 0),
            status=metadata["status"],
            approved=metadata.get("approved"),
            access_level=metadata.get("access_level"),
            uploaded_at=metadata.get("uploaded_at"),
            processed_at=metadata.get("processed_at"),
            match_fields=match_fields,
        )

    @staticmethod
    def _detail_schema(detail: dict) -> DocumentDetailRead:
        return DocumentDetailRead(
            id=detail["id"],
            status=detail["status"],
            approved=detail.get("approved"),
            access_level=detail.get("access_level"),
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
                source_url=(
                    detail.get("source_url")
                    or detail.get("metadata_json", {}).get("source_url")
                ),
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
            id=row["chunk_id"],
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


document_catalogue_repository = DocumentCatalogueRepository()
