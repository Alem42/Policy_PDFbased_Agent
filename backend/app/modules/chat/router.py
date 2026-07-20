import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import get_current_user
from app.modules.chat.rag.graph.workflow import run_pdf_qa
from app.modules.chat.schemas import MAX_HISTORY_TURNS, ChatRequest, ChatResponse, Citation

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

    # Trim history to the last MAX_HISTORY_TURNS turns (user + assistant pairs).
    # Each turn is 2 messages, so we keep the last MAX_HISTORY_TURNS * 2 messages.
    raw_history = [msg.model_dump() for msg in payload.history]
    trimmed_history = raw_history[-(MAX_HISTORY_TURNS * 2):]

    try:
        # run_pdf_qa is synchronous (LangGraph + CPU-bound embedding/reranking).
        # Running it in a thread pool prevents blocking the async event loop.
        result = await asyncio.to_thread(
            run_pdf_qa,
            question=payload.question,
            document_ids=identifiers,
            model=payload.model,
            response_mode=payload.response_mode,
            answer_mode=payload.answer_mode,
            top_k=payload.top_k,
            include_restricted=user["role"] == "admin",
            history=trimmed_history,
        )
        return ChatResponse(
            answer=result["answer"],
            citations=[Citation(**citation) for citation in result.get("citations", [])],
            truncated=result.get("truncated", False),
            evidence_sufficient=result.get("evidence_sufficient", True),
            response_mode=payload.response_mode,
            answer_mode=payload.answer_mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model request failed: {exc}") from exc
