from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.schemas.document import DocumentRead

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    policy_area: str | None = None,
    country_or_region: str | None = None,
    source_organisation: str | None = None,
    tag: str | None = None,
) -> list[DocumentRead]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document library placeholder. Implement in feature/document-library.",
    )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID) -> DocumentRead:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document detail placeholder. Implement in feature/document-library.",
    )
