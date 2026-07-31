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
        agent_mode: str | None = None,
        evidence_sources: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> str:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO chat_messages
                    (id, session_id, role, content, citations_json,
                     evidence_sufficient, response_mode, answer_mode, model, agent_mode,
                     evidence_sources, suggestions_json)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
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
                    agent_mode,
                    json.dumps(evidence_sources or []),
                    json.dumps(suggestions or []),
                ),
            ).fetchone()
            conn.commit()
        return str(row["id"])

    def create_pending_message(
        self, session_id: str, role: str = "assistant", agent_mode: str = "react"
    ) -> str:
        """Insert a placeholder row the moment an assistant turn starts.

        Its reasoning_steps/content are filled in afterwards via
        update_reasoning_steps (once per tool call) and finalize_message
        (once the answer is done) — so a turn interrupted or crashed
        mid-stream still leaves a readable partial trace in history instead
        of nothing at all.
        """
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, status, agent_mode)
                VALUES (%s, %s, %s, '', 'streaming', %s)
                RETURNING id
                """,
                (str(uuid4()), session_id, role, agent_mode),
            ).fetchone()
            conn.commit()
        return str(row["id"])

    def update_reasoning_steps(self, message_id: str, steps: list[dict]) -> None:
        """Overwrite a pending message's trace — called once per tool call."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_messages SET reasoning_steps = %s::jsonb WHERE id = %s",
                (json.dumps(steps), message_id),
            )
            conn.commit()

    def finalize_message(
        self,
        message_id: str,
        content: str,
        citations: list[dict] | None = None,
        evidence_sufficient: bool | None = None,
        response_mode: str | None = None,
        answer_mode: str | None = None,
        model: str | None = None,
        status: str = "complete",
        evidence_sources: list[str] | None = None,
    ) -> None:
        """Fill in a pending message's final answer, closing out the turn
        started by create_pending_message."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE chat_messages
                SET content = %s, citations_json = %s::jsonb, evidence_sufficient = %s,
                    response_mode = %s, answer_mode = %s, model = %s, status = %s,
                    evidence_sources = %s::jsonb
                WHERE id = %s
                """,
                (
                    content,
                    json.dumps(citations or []),
                    evidence_sufficient,
                    response_mode,
                    answer_mode,
                    model,
                    status,
                    json.dumps(evidence_sources or []),
                    message_id,
                ),
            )
            conn.commit()

    def touch_session(self, session_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = now() WHERE id = %s",
                (session_id,),
            )
            conn.commit()

    def update_message_suggestions(
        self,
        message_id: str,
        suggestions: list[str],
    ) -> bool:
        """Attach asynchronously generated suggestions to an assistant message."""
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE chat_messages
                SET suggestions_json = %s::jsonb
                WHERE id = %s AND role = 'assistant'
                RETURNING id
                """,
                (json.dumps(suggestions), message_id),
            ).fetchone()
            conn.commit()
        return row is not None

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
                       evidence_sufficient, response_mode, answer_mode, model,
                       reasoning_steps, status, agent_mode, evidence_sources,
                       suggestions_json, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return dict(session), [dict(m) for m in msgs]

    def get_message_steps(self, message_id: str) -> list[dict]:
        """Current reasoning_steps for a (possibly still-streaming) message —
        the seed a resumed turn appends onto after an ask_user/confirm_import
        interrupt, so earlier steps aren't lost."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT reasoning_steps FROM chat_messages WHERE id = %s",
                (message_id,),
            ).fetchone()
        if not row or not row["reasoning_steps"]:
            return []
        steps = row["reasoning_steps"]
        return steps if isinstance(steps, list) else json.loads(steps)

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
