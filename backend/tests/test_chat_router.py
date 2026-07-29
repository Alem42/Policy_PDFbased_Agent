import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.messages import ToolMessage

from app.modules.chat import router as chat_router
from app.modules.chat.schemas import ChatRequest


def test_tool_result_event_exposes_compact_trace_summary() -> None:
    message = ToolMessage(
        content=json.dumps(
            {
                "evidence_sufficient": False,
                "reason": "The excerpts do not mention UK space policy.",
                "results": [
                    {"title": "Space Strategy", "number": 1},
                    {"title": "Space Strategy", "number": 2},
                    {"title": "Defence Space", "number": 3},
                ],
            }
        ),
        tool_call_id="call-1",
        name="search_full_corpus",
    )

    assert chat_router._tool_result_event(message) == {
        "type": "tool_result",
        "tool": "search_full_corpus",
        "evidence_sufficient": False,
        "evidence_reason": "The excerpts do not mention UK space policy.",
        "result_count": 3,
        "source_titles": ["Space Strategy", "Defence Space"],
        "answer_plan": None,
        "citation_numbers": None,
    }


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
