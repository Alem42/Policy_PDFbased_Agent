"""Failure-isolated PostgreSQL adapter for the RunEventSink contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.modules.chat.runtime.context import AgentRunContext
from app.modules.chat.runtime.events import RunEvent
from app.modules.chat.runtime.repository import AgentRunRepository, agent_run_repository


@dataclass
class PostgresRunEventSink:
    context: AgentRunContext
    repository: AgentRunRepository = field(default_factory=lambda: agent_run_repository)
    _run_ensured: bool = field(default=False, init=False)

    async def emit(self, event: RunEvent) -> None:
        if event.run_id != self.context.run_id:
            raise ValueError("Event run_id does not match sink context.")
        if not self._run_ensured:
            await asyncio.to_thread(self.repository.ensure_run, self.context)
            self._run_ensured = True
        await asyncio.to_thread(self.repository.append_event, event)
