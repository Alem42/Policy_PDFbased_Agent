"""PostgreSQL persistence for sanitized agent run metadata and events."""

from __future__ import annotations

import json

from app.core.database import get_connection
from app.modules.chat.runtime.context import AgentRunContext
from app.modules.chat.runtime.events import RunEvent


class AgentRunRepository:
    def ensure_run(self, context: AgentRunContext) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, session_id, assistant_message_id, user_id, is_admin,
                    profile, model, prompt_version, configuration_version
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE
                SET updated_at = now()
                """,
                (
                    context.run_id,
                    context.session_id,
                    context.assistant_message_id,
                    context.user_id,
                    context.is_admin,
                    json.dumps(context.as_dict()["profile"]),
                    context.model,
                    context.prompt_version,
                    context.configuration_version,
                ),
            )
            connection.commit()

    def append_event(self, event: RunEvent) -> int:
        """Append atomically and assign the next sequence, including on resume."""

        with get_connection() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (event.run_id,),
            )
            row = connection.execute(
                """
                INSERT INTO agent_run_events (
                    run_id, sequence, event_type, occurred_at, node_name,
                    tool_name, duration_ms, token_usage, status, error_type,
                    public_metadata
                )
                SELECT %s, COALESCE(MAX(sequence), 0) + 1, %s, %s, %s,
                       %s, %s, %s::jsonb, %s, %s, %s::jsonb
                FROM agent_run_events
                WHERE run_id = %s
                RETURNING sequence
                """,
                (
                    event.run_id,
                    event.event_type,
                    event.occurred_at,
                    event.node_name,
                    event.tool_name,
                    event.duration_ms,
                    json.dumps(event.token_usage),
                    event.status,
                    event.error_type,
                    json.dumps(event.public_metadata),
                    event.run_id,
                ),
            ).fetchone()
            connection.commit()
        return int(row["sequence"])

    def list_runs(self, limit: int = 50) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT r.*,
                       COUNT(e.id)::integer AS event_count,
                       MAX(e.occurred_at) AS last_event_at
                FROM agent_runs r
                LEFT JOIN agent_run_events e ON e.run_id = r.run_id
                GROUP BY r.run_id
                ORDER BY r.started_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with get_connection() as connection:
            run = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            events = connection.execute(
                """
                SELECT sequence, event_type, occurred_at, node_name, tool_name,
                       duration_ms, token_usage, status, error_type, public_metadata
                FROM agent_run_events
                WHERE run_id = %s
                ORDER BY sequence ASC
                """,
                (run_id,),
            ).fetchall()
        return {"run": dict(run), "events": [dict(event) for event in events]}


agent_run_repository = AgentRunRepository()
