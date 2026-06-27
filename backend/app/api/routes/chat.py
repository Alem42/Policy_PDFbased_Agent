from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies.auth import get_current_user
from app.rag.graph.workflow import run_pdf_qa
from app.schemas.chat import ChatRequest, ChatResponse, Citation

router = APIRouter(tags=["rag"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: CurrentUser,
) -> ChatResponse:
    identifiers = [str(document_id) for document_id in payload.document_ids]
    if not identifiers and payload.filenames:
        identifiers = payload.filenames
    if not identifiers:
        raise HTTPException(status_code=400, detail="At least one document must be selected.")

    try:
        result = run_pdf_qa(
            question=payload.question,
            document_ids=identifiers,
            model=payload.model,
            top_k=payload.top_k,
            include_restricted=user["role"] == "admin",
        )
        return ChatResponse(
            answer=result["answer"],
            citations=[Citation(**citation) for citation in result.get("citations", [])],
            truncated=result.get("truncated", False),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model request failed: {exc}") from exc
