"""POST /chat/resume: session ownership and paused-turn checks."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.chat import router as chat_router
from app.modules.chat.application import streaming
from app.modules.chat.schemas import ResumeChatRequest


@pytest.mark.asyncio
async def test_chat_resume_rejects_session_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository, "session_belongs_to_user", lambda *_: False
    )

    payload = ResumeChatRequest(session_id=uuid4(), answer="Yes")

    with pytest.raises(HTTPException) as exc_info:
        await chat_router.chat_resume(payload, {"id": str(uuid4()), "role": "user"})

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_resume_rejects_when_no_paused_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_router.chat_turn_service.repository, "session_belongs_to_user", lambda *_: True
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


@pytest.mark.asyncio
async def test_closing_interrupt_stream_does_not_fail_paused_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGraph:
        async def astream(self, graph_input, *, config, stream_mode):
            yield "updates", {
                "__interrupt__": (SimpleNamespace(value={"type": "confirm_import"}),)
            }

    async def message_steps(_message_id):
        return []

    failed_messages = []

    async def fail(message_id, content=""):
        failed_messages.append((message_id, content))

    monkeypatch.setattr(streaming.react_orchestrator, "graph", lambda: FakeGraph())
    monkeypatch.setattr(streaming.chat_turn_service, "message_steps", message_steps)
    monkeypatch.setattr(streaming.chat_turn_service, "fail", fail)

    events = streaming.stream_agent_events(
        {},
        config={"configurable": {"thread_id": "session-1"}},
        session_id="session-1",
        response_mode="researcher",
        answer_mode="analysis",
        assistant_message_id="message-1",
    )

    first_event = await anext(events)
    await events.aclose()

    assert '"type": "confirm_import"' in first_event
    assert failed_messages == []
