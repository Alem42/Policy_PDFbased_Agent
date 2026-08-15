"""Stable runtime contracts shared by chat execution paths."""

from app.modules.chat.runtime.context import AgentRunContext, build_agent_run_context
from app.modules.chat.runtime.events import RunEvent, RunEventFactory
from app.modules.chat.runtime.postgres_sink import PostgresRunEventSink
from app.modules.chat.runtime.sink import (
    CompositeRunEventSink,
    InMemoryRunEventSink,
    NullRunEventSink,
    RunEventSink,
    emit_safely,
)
from app.modules.chat.runtime.versioning import (
    PROMPT_VERSION,
    stable_configuration_version,
)

__all__ = [
    "PROMPT_VERSION",
    "AgentRunContext",
    "CompositeRunEventSink",
    "InMemoryRunEventSink",
    "NullRunEventSink",
    "PostgresRunEventSink",
    "RunEvent",
    "RunEventFactory",
    "RunEventSink",
    "build_agent_run_context",
    "emit_safely",
    "stable_configuration_version",
]
