from __future__ import annotations

import json
from uuid import uuid4

from app.core.database import get_connection

MAX_HISTORY_TURNS = 5  # mirrored from schemas.py to avoid circular import


class ChatHistoryRepository:
    """Persistence for chat sessions and messages."""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        title: str,
        document_ids: list[str],
        response_mode: str,
    ) -> str:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO chat_sessions (id, user_id, title, document_ids, response_mode)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (str(uuid4()), user_id, title[:200], document_ids, response_mode),
            ).fetchone()
            conn.commit()
        return str(row["id"])

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
        evidence_sufficient: bool | None = None,
        response_mode: str | None = None,
        answer_mode: str | None = None,
        model: str | None = None,
    ) -> str:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO chat_messages
                    (id, session_id, role, content, citations_json,
                     evidence_sufficient, response_mode, answer_mode, model)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(uuid4()),
                    session_id,
                    role,
                    content,
                    json.dumps(citations or []),
                    evidence_sufficient,
                    response_mode,
                    answer_mode,
                    model,
                ),
            ).fetchone()
            conn.commit()
        return str(row["id"])

    def touch_session(self, session_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = now() WHERE id = %s",
                (session_id,),
            )
            conn.commit()

    def delete_session(self, session_id: str, user_id: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "DELETE FROM chat_sessions WHERE id = %s AND user_id = %s RETURNING id",
                (session_id, user_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def rename_session(self, session_id: str, user_id: str, title: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE chat_sessions SET title = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (title[:200], session_id, user_id),
            ).fetchone()
            conn.commit()
        return row is not None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            ).fetchone()
        return row is not None

    def list_sessions(self, user_id: str, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id, s.title, s.document_ids, s.response_mode,
                    s.created_at, s.updated_at,
                    last_msg.content AS last_message_preview
                FROM chat_sessions s
                LEFT JOIN LATERAL (
                    SELECT content FROM chat_messages
                    WHERE session_id = s.id
                    ORDER BY created_at DESC LIMIT 1
                ) last_msg ON true
                WHERE s.user_id = %s
                ORDER BY s.updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
        return [
            {
                **dict(row),
                "id": str(row["id"]),
                "last_message_preview": (row["last_message_preview"] or "")[:120],
            }
            for row in rows
        ]

    def get_session_messages(self, session_id: str, user_id: str) -> tuple[dict | None, list[dict]]:
        """Return (session_meta, messages). session_meta is None if not found or wrong user."""
        with get_connection() as conn:
            session = conn.execute(
                "SELECT * FROM chat_sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            ).fetchone()
            if session is None:
                return None, []
            msgs = conn.execute(
                """
                SELECT id, session_id, role, content, citations_json,
                       evidence_sufficient, response_mode, answer_mode, model, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return dict(session), [dict(m) for m in msgs]

    def get_history_for_llm(
        self, session_id: str, max_turns: int = MAX_HISTORY_TURNS
    ) -> list[dict]:
        """Return the last max_turns*2 messages as {role, content} dicts for the LLM."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (session_id, max_turns * 2),
            ).fetchall()
        # Rows are newest-first; reverse for chronological order
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


chat_history_repository = ChatHistoryRepository()
