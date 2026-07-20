import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import get_current_user
from app.modules.chat.history_repository import chat_history_repository
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

    user_id = str(user["id"])

    # ── Session management ──────────────────────────────────────────────
    if payload.session_id is not None:
        session_id = str(payload.session_id)
        # Read history from DB (more reliable than relying on the client to resend it).
        history = await asyncio.to_thread(
            chat_history_repository.get_history_for_llm,
            session_id,
            MAX_HISTORY_TURNS,
        )
    else:
        session_id = await asyncio.to_thread(
            chat_history_repository.create_session,
            user_id,
            payload.question[:80],
            identifiers,
            payload.response_mode,
        )
        # New session — no prior history.
        history = []

    # ── Save the user question immediately ─────────────────────────────
    await asyncio.to_thread(
        chat_history_repository.add_message,
        session_id, "user", payload.question,
    )

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
            history=history,
        )

        citations = [Citation(**c) for c in result.get("citations", [])]
        evidence_sufficient = result.get("evidence_sufficient", True)

        # ── Save the assistant answer ───────────────────────────────────
        await asyncio.to_thread(
            chat_history_repository.add_message,
            session_id,
            "assistant",
            result["answer"],
            result.get("citations", []),
            evidence_sufficient,
            payload.response_mode,
        )
        await asyncio.to_thread(chat_history_repository.touch_session, session_id)

        from uuid import UUID
        return ChatResponse(
            answer=result["answer"],
            citations=citations,
            truncated=result.get("truncated", False),
            evidence_sufficient=evidence_sufficient,
            evidence_reason=result.get("evidence_reason"),
            response_mode=payload.response_mode,
            answer_mode=payload.answer_mode,
            session_id=UUID(session_id),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model request failed: {exc}") from exc
