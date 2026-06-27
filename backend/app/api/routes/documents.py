import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.schemas.document import DocumentRead
from app.services.auth_service import get_current_user, get_optional_user
from app.services.document_service import (
    extract_pages,
    get_document_chunks,
    get_document_detail,
    resolve_pdf,
)
from app.services.document_service import (
    list_documents as list_document_records,
)

router = APIRouter(prefix="/documents", tags=["documents"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(get_optional_user)]


def _document_read(row: dict) -> DocumentRead:
    policy_areas = row.get("policy_areas") or []
    keywords = row.get("keywords") or []
    return DocumentRead(
        id=row["id"],
        title=row.get("title") or row.get("original_filename") or row.get("name"),
        name=row.get("name") or row.get("original_filename"),
        original_filename=row.get("original_filename"),
        stored_filename=row.get("stored_filename"),
        relative_path=row.get("relative_path"),
        size=row.get("size"),
        modified_at=row.get("modified_at"),
        summary=row.get("summary"),
        source_type=row.get("source_type"),
        source_organisation=row.get("source_organisation"),
        source_url=None,
        policy_area=(policy_areas or [None])[0],
        policy_areas=policy_areas,
        country_or_region=row.get("country_region"),
        country_region=row.get("country_region"),
        language=row.get("language"),
        published_year=row.get("year"),
        year=row.get("year"),
        tags=keywords,
        keywords=keywords,
        credibility_level=row.get("source_type") or "unknown",
        processing_status=row.get("status") or "uploaded",
        page_count=row.get("page_count") or 0,
        chunk_count=row.get("chunk_count") or 0,
        approved=row.get("approved", True),
        access_level=row.get("access_level", "public"),
        processed_at=row.get("processed_at"),
        error_message=row.get("error_message"),
        publication_date=row.get("publication_date"),
        metadata_json=row.get("metadata_json") or {},
        status=row.get("status") or "uploaded",
        uploaded_at=row.get("uploaded_at"),
    )


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    user: OptionalUser,
    policy_area: str | None = None,
    country_or_region: str | None = None,
    source_organisation: str | None = None,
    tag: str | None = None,
) -> list[DocumentRead]:
    try:
        rows = await asyncio.to_thread(
            list_document_records,
            include_restricted=bool(user and user["role"] == "admin"),
            policy_area=policy_area,
            country_or_region=country_or_region,
            source_organisation=source_organisation,
            tag=tag,
        )
        return [_document_read(row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    user: OptionalUser,
) -> DocumentRead:
    try:
        row = await asyncio.to_thread(
            get_document_detail,
            str(document_id),
            include_restricted=bool(user and user["role"] == "admin"),
        )
        return _document_read(row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: UUID,
    user: CurrentUser,
) -> FileResponse:
    try:
        include_restricted = user["role"] == "admin"
        row = await asyncio.to_thread(
            get_document_detail, str(document_id), include_restricted=include_restricted
        )
        path = await asyncio.to_thread(
            resolve_pdf, str(document_id), include_restricted=include_restricted
        )
        return FileResponse(path, media_type="application/pdf", filename=row["original_filename"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: UUID,
    user: CurrentUser,
) -> dict:
    try:
        include_restricted = user["role"] == "admin"
        row = await asyncio.to_thread(
            get_document_detail, str(document_id), include_restricted=include_restricted
        )
        pages = await asyncio.to_thread(
            extract_pages, str(document_id), include_restricted=include_restricted
        )
        return {
            "filename": row["original_filename"],
            "document_id": row["id"],
            "page_count": len(pages),
            "extractable_page_count": sum(bool(page["text"]) for page in pages),
            "pages": pages,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{document_id}/chunks")
async def list_document_chunks(
    document_id: UUID,
    user: OptionalUser,
) -> list[dict]:
    try:
        return await asyncio.to_thread(
            get_document_chunks,
            str(document_id),
            include_restricted=bool(user and user["role"] == "admin"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
