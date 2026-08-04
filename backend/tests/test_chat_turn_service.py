from __future__ import annotations

import pytest

from app.modules.chat.application.models import StartTurnRequest
from app.modules.chat.application.turn_service import ChatTurnService, SessionNotFoundError


class FakeHistoryRepository:
    def __init__(self, *, owns: bool = True) -> None:
        self.owns = owns
        self.messages = [{"role": "assistant", "content": "Previous answer"}]
        self.calls: list[str] = []

    def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        self.calls.append("owns")
        return self.owns

    def get_history_for_llm(self, session_id: str, limit: int) -> list[dict]:
        self.calls.append("history")
        return list(self.messages)

    def update_session_document_ids(self, session_id: str, document_ids: list[str]) -> None:
        self.calls.append("update_document_ids")
        self.last_document_ids = document_ids

    def create_session(self, *args) -> str:
        self.calls.append("create_session")
        return "new-session"

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.calls.append("add_message")
        self.messages.append({"role": role, "content": content})

    def create_pending_message(self, session_id: str, role: str, agent_mode: str) -> str:
        self.calls.append("pending")
        return "assistant-message"


def request(**overrides) -> StartTurnRequest:
    values = {
        "user_id": "user-1",
        "question": "Current question",
        "identifiers": ("doc-1",),
        "response_mode": "researcher",
        "agent_mode": "react",
        "session_id": "session-1",
        "create_pending_assistant": True,
    }
    values.update(overrides)
    return StartTurnRequest(**values)


@pytest.mark.asyncio
async def test_start_reads_prior_history_before_inserting_current_question() -> None:
    repository = FakeHistoryRepository()
    turn = await ChatTurnService(repository).start(request())

    assert repository.calls == ["owns", "history", "update_document_ids", "add_message", "pending"]
    assert turn.history == [{"role": "assistant", "content": "Previous answer"}]
    assert all(item["content"] != "Current question" for item in turn.history)
    assert repository.messages[-1] == {"role": "user", "content": "Current question"}
    assert turn.assistant_message_id == "assistant-message"


@pytest.mark.asyncio
async def test_start_rejects_session_owned_by_another_user_without_writing() -> None:
    repository = FakeHistoryRepository(owns=False)
    with pytest.raises(SessionNotFoundError):
        await ChatTurnService(repository).start(request())
    assert repository.calls == ["owns"]


@pytest.mark.asyncio
async def test_start_creates_new_session_with_empty_prior_history() -> None:
    repository = FakeHistoryRepository()
    turn = await ChatTurnService(repository).start(
        request(session_id=None, create_pending_assistant=False)
    )
    assert repository.calls == ["create_session", "add_message"]
    assert turn.session_id == "new-session"
    assert turn.history == []


@pytest.mark.asyncio
async def test_start_syncs_document_ids_to_the_current_turns_selection() -> None:
    """Sources added or removed mid-conversation must land in history, not just
    the set picked when the session was first created."""
    repository = FakeHistoryRepository()
    await ChatTurnService(repository).start(request(identifiers=("doc-2", "doc-3")))
    assert repository.last_document_ids == ["doc-2", "doc-3"]


@pytest.mark.asyncio
async def test_start_does_not_touch_document_ids_when_turn_has_none() -> None:
    """A resume/interrupt turn with no identifiers must not wipe the session's
    stored document set."""
    repository = FakeHistoryRepository()
    await ChatTurnService(repository).start(request(identifiers=()))
    assert "update_document_ids" not in repository.calls
