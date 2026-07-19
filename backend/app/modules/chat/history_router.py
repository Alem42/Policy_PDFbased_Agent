import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import get_current_user
from app.modules.chat.history_repository import chat_history_repository
from app.modules.chat.schemas import (
    Citation,
    SessionDetail,
    SessionMessage,
    SessionRenameRequest,
    SessionSummary,
)

router = APIRouter(prefix="/chat", tags=["chat-history"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(user: CurrentUser) -> list[SessionSummary]:
    rows = await asyncio.to_thread(
        chat_history_repository.list_sessions,
        str(user["id"]),
    )
    return [
        SessionSummary(
            id=UUID(str(row["id"])),
            title=row["title"],
            document_ids=list(row["document_ids"] or []),
            response_mode=row["response_mode"],
            last_message_preview=row.get("last_message_preview"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: UUID, user: CurrentUser) -> SessionDetail:
    session, msgs = await asyncio.to_thread(
        chat_history_repository.get_session_messages,
        str(session_id),
        str(user["id"]),
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = [
        SessionMessage(
            id=UUID(str(m["id"])),
            session_id=UUID(str(m["session_id"])),
            role=m["role"],
            content=m["content"],
            citations=_parse_citations(m.get("citations_json")),
            evidence_sufficient=m.get("evidence_sufficient"),
            response_mode=m.get("response_mode"),
            created_at=m["created_at"],
        )
        for m in msgs
    ]
    return SessionDetail(
        id=UUID(str(session["id"])),
        title=session["title"],
        document_ids=list(session["document_ids"] or []),
        response_mode=session["response_mode"],
        messages=messages,
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID, user: CurrentUser) -> None:
    deleted = await asyncio.to_thread(
        chat_history_repository.delete_session,
        str(session_id),
        str(user["id"]),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")


@router.patch("/sessions/{session_id}/title", status_code=204)
async def rename_session(
    session_id: UUID,
    payload: SessionRenameRequest,
    user: CurrentUser,
) -> None:
    updated = await asyncio.to_thread(
        chat_history_repository.rename_session,
        str(session_id),
        str(user["id"]),
        payload.title,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found.")


# ---------------------------------------------------------------------------

def _parse_citations(raw) -> list[Citation]:
    if not raw:
        return []
    try:
        data = raw if isinstance(raw, list) else json.loads(raw)
        return [Citation(**c) for c in data]
    except Exception:
        return []
