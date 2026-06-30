from uuid import uuid4

from app.modules.documents.admin_schemas import (
    AdminDocumentCreateResponse,
    DocumentProcessingStatus,
)
from app.modules.documents.schemas import (
    DocumentChunkRead,
    DocumentDetailRead,
    DocumentMetadataRead,
    DocumentSearchResultRead,
    DocumentSourceInfoRead,
)


def test_document_resource_responses_use_id() -> None:
    document_id = uuid4()
    responses = [
        AdminDocumentCreateResponse(id=document_id),
        DocumentProcessingStatus(id=document_id, status="indexed"),
        DocumentSearchResultRead(
            id=document_id,
            original_filename="policy.pdf",
            status="ready",
        ),
        DocumentDetailRead(
            id=document_id,
            status="ready",
            metadata=DocumentMetadataRead(),
            source=DocumentSourceInfoRead(),
        ),
    ]

    for response in responses:
        payload = response.model_dump(mode="json")
        assert payload["id"] == str(document_id)
        assert "document_id" not in payload


def test_chunk_uses_id_and_keeps_document_foreign_key() -> None:
    chunk_id = uuid4()
    document_id = uuid4()
    chunk = DocumentChunkRead(
        id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        text="Policy excerpt",
    )

    payload = chunk.model_dump(mode="json")
    assert payload["id"] == str(chunk_id)
    assert payload["document_id"] == str(document_id)
    assert "chunk_id" not in payload
