from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings
from app.core.database import normalise_database_url

_saver: AsyncPostgresSaver | None = None
_connection_cm = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """Open the persistent Postgres-backed LangGraph checkpointer.

    Uses langgraph-checkpoint-postgres's own `.setup()` (idempotent) to create
    its tables, rather than a project migration — that schema is internal to
    LangGraph and versioned by that package, not something to hand-maintain
    alongside the app's own tables. `thread_id` for the agent graph is the
    existing chat `session_id` (see chat/rag/agent/graph.py), so no new id
    concept is introduced.

    Call once from the FastAPI lifespan; the connection is kept open for the
    process lifetime and reused by every graph invocation/resume.
    """
    global _saver, _connection_cm
    if _saver is not None:
        return _saver
    dsn = normalise_database_url(get_settings().database_url)
    _connection_cm = AsyncPostgresSaver.from_conn_string(dsn)
    _saver = await _connection_cm.__aenter__()
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _saver, _connection_cm
    if _connection_cm is not None:
        await _connection_cm.__aexit__(None, None, None)
    _saver = None
    _connection_cm = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialized — call init_checkpointer() at startup.")
    return _saver
