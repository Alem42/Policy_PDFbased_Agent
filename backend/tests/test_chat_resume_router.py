"""POST /chat/resume: session ownership and paused-turn checks."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.chat import router as chat_router
from app.modules.chat.schemas import ResumeChatRequest


@pytest.mark.asyncio
async def test_chat_resume_rejects_session_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_router.chat_history_repository, "session_belongs_to_user", lambda *_: False
    )

    payload = ResumeChatRequest(session_id=uuid4(), answer="Yes")

    with pytest.raises(HTTPException) as exc_info:
        await chat_router.chat_resume(payload, {"id": str(uuid4()), "role": "user"})

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_resume_rejects_when_no_paused_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_router.chat_history_repository, "session_belongs_to_user", lambda *_: True
    )

    class FakeGraph:
        async def aget_state(self, config):
            # next == () means no pending interrupted task for this thread.
            return SimpleNamespace(next=(), values={})

    monkeypatch.setattr(chat_router, "get_agent_graph", lambda: FakeGraph())

    payload = ResumeChatRequest(session_id=uuid4(), answer="Yes")

    with pytest.raises(HTTPException) as exc_info:
        await chat_router.chat_resume(payload, {"id": str(uuid4()), "role": "user"})

    assert exc_info.value.status_code == 409
