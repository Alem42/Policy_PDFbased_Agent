from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.chat import router as chat_router
from app.modules.chat.schemas import ChatRequest


@pytest.mark.asyncio
async def test_chat_rejects_session_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_session_belongs_to_user(session_id: str, user_id: str) -> bool:
        return False

    def fail_get_history_for_llm(*_: object) -> list[dict]:
        raise AssertionError("History should not be read for another user's session.")

    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "session_belongs_to_user",
        fake_session_belongs_to_user,
    )
    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "get_history_for_llm",
        fail_get_history_for_llm,
    )

    payload = ChatRequest(
        question="What does this policy say?",
        document_ids=[uuid4()],
        session_id=uuid4(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat_router.chat(
            payload,
            {"id": str(uuid4()), "role": "user"},
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Session not found."
