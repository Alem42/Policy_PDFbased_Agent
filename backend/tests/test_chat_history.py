"""Integration tests for chat history repository (hits the real database)."""
from __future__ import annotations

import pytest

from app.modules.chat.history_repository import ChatHistoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo() -> ChatHistoryRepository:
    return ChatHistoryRepository()


def _find_test_user() -> str:
    """Return the id of any existing user for FK validity."""
    from app.core.database import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT id FROM app_users LIMIT 1").fetchone()
    if row is None:
        pytest.skip("No users in database — cannot test chat history FK constraints.")
    return str(row["id"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_session_returns_uuid():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(
        user_id=user_id,
        title="Test session",
        document_ids=["doc-1", "doc-2"],
        response_mode="researcher",
    )
    assert len(session_id) == 36  # UUID string length
    # Cleanup
    repo.delete_session(session_id, user_id)


def test_add_and_retrieve_messages():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Retrieval test", [], "researcher")

    repo.add_message(session_id, "user", "What is climate policy?")
    repo.add_message(
        session_id,
        "assistant",
        "Climate policy refers to...",
        citations=[{"title": "Doc A", "page": 3}],
        evidence_sufficient=True,
        response_mode="researcher",
    )

    _, msgs = repo.get_session_messages(session_id, user_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is climate policy?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["evidence_sufficient"] is True

    # Cleanup
    repo.delete_session(session_id, user_id)


def test_get_history_for_llm_order_and_limit():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "History order test", [], "researcher")

    # Insert 4 turns (8 messages), ask for max 2 turns (4 messages)
    for i in range(4):
        repo.add_message(session_id, "user", f"Question {i}")
        repo.add_message(session_id, "assistant", f"Answer {i}")

    history = repo.get_history_for_llm(session_id, max_turns=2)
    assert len(history) == 4  # 2 turns × 2 messages
    # Must be in chronological order (oldest first)
    assert history[0]["content"] == "Question 2"
    assert history[1]["content"] == "Answer 2"
    assert history[2]["content"] == "Question 3"
    assert history[3]["content"] == "Answer 3"

    repo.delete_session(session_id, user_id)


def test_list_sessions_newest_first():
    repo = _make_repo()
    user_id = _find_test_user()

    id_a = repo.create_session(user_id, "Session A", [], "researcher")
    id_b = repo.create_session(user_id, "Session B", [], "student")
    # Touch B to make it the most-recently-updated
    repo.touch_session(id_b)

    sessions = repo.list_sessions(user_id, limit=10)
    ids = [str(s["id"]) for s in sessions]
    assert ids.index(id_b) < ids.index(id_a)  # B is newer

    repo.delete_session(id_a, user_id)
    repo.delete_session(id_b, user_id)


def test_list_sessions_includes_preview():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Preview test", [], "researcher")
    repo.add_message(session_id, "user", "Hello preview message")
    repo.add_message(session_id, "assistant", "This is the last message")

    sessions = repo.list_sessions(user_id, limit=20)
    match = next((s for s in sessions if str(s["id"]) == session_id), None)
    assert match is not None
    assert match["last_message_preview"] == "This is the last message"

    repo.delete_session(session_id, user_id)


def test_delete_session_cascades_messages():
    from app.core.database import get_connection

    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Cascade test", [], "researcher")
    repo.add_message(session_id, "user", "Will be deleted")

    deleted = repo.delete_session(session_id, user_id)
    assert deleted is True

    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = %s",
            (session_id,),
        ).fetchone()["n"]
    assert count == 0


def test_delete_wrong_user_returns_false():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Auth test", [], "researcher")

    wrong_user_id = "00000000-0000-0000-0000-000000000000"
    result = repo.delete_session(session_id, wrong_user_id)
    assert result is False  # Cannot delete another user's session

    # Cleanup with real owner
    repo.delete_session(session_id, user_id)


def test_rename_session():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Original title", [], "researcher")

    updated = repo.rename_session(session_id, user_id, "Renamed title")
    assert updated is True

    session, _ = repo.get_session_messages(session_id, user_id)
    assert session["title"] == "Renamed title"

    repo.delete_session(session_id, user_id)


def test_get_session_wrong_user_returns_none():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Private", [], "researcher")

    wrong = "00000000-0000-0000-0000-000000000000"
    session, msgs = repo.get_session_messages(session_id, wrong)
    assert session is None
    assert msgs == []

    repo.delete_session(session_id, user_id)


def test_session_belongs_to_user_requires_owner():
    repo = _make_repo()
    user_id = _find_test_user()
    session_id = repo.create_session(user_id, "Ownership check", [], "researcher")

    wrong = "00000000-0000-0000-0000-000000000000"
    assert repo.session_belongs_to_user(session_id, user_id) is True
    assert repo.session_belongs_to_user(session_id, wrong) is False

    repo.delete_session(session_id, user_id)
