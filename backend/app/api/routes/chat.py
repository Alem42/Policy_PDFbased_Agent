from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.schemas.chat import ChatRequest, ChatResponse, DocumentChunkRead

router = APIRouter(tags=["rag"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="RAG chat placeholder. Implement in feature/rag-chat.",
    )


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkRead])
async def list_document_chunks(document_id: UUID) -> list[DocumentChunkRead]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chunk listing placeholder. Implement in feature/ingestion-pipeline.",
    )
