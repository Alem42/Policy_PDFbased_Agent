"""Small instrumentation facade used by Direct and ReAct application drivers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.modules.chat.runtime.context import AgentRunContext
from app.modules.chat.runtime.events import RunEventFactory, RunEventType
from app.modules.chat.runtime.sink import NullRunEventSink, RunEventSink, emit_safely


@dataclass
class RunObserver:
    context: AgentRunContext
    sink: RunEventSink = field(default_factory=NullRunEventSink)
    _factory: RunEventFactory = field(init=False)
    _started_at: float = field(default_factory=time.perf_counter, init=False)
    _first_token_emitted: bool = field(default=False, init=False)
    _terminal_emitted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._factory = RunEventFactory(self.context.run_id)

    async def emit(self, event_type: RunEventType, **kwargs: Any) -> None:
        await emit_safely(self.sink, self._factory.create(event_type, **kwargs))

    async def start(self, *, resumed: bool = False) -> None:
        if resumed:
            return
        profile = self.context.profile
        await self.emit(
            "run_started",
            status="started",
            public_metadata={
                "workflow_mode": profile.workflow_mode,
                "source_policy": profile.source_policy,
                "output_format": profile.output_format,
                "model": self.context.model,
            },
        )

    async def first_token(self, *, node_name: str | None = None) -> None:
        if self._first_token_emitted:
            return
        self._first_token_emitted = True
        await self.emit(
            "first_token",
            node_name=node_name,
            duration_ms=elapsed_ms(self._started_at),
        )

    async def finish(
        self,
        *,
        token_usage: dict[str, int] | None = None,
        public_metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        await self.emit(
            "run_finished",
            duration_ms=elapsed_ms(self._started_at),
            token_usage=token_usage or {},
            status="succeeded",
            public_metadata=public_metadata or {},
        )

    async def fail(self, error: BaseException) -> None:
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        await self.emit(
            "run_failed",
            duration_ms=elapsed_ms(self._started_at),
            status="failed",
            error_type=type(error).__name__,
        )


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)
