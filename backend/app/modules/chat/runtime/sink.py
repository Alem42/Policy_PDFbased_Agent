"""Replaceable and failure-isolated destinations for run events."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.modules.chat.runtime.events import RunEvent

logger = logging.getLogger(__name__)


class RunEventSink(Protocol):
    async def emit(self, event: RunEvent) -> None: ...


class NullRunEventSink:
    async def emit(self, event: RunEvent) -> None:
        return None


@dataclass
class InMemoryRunEventSink:
    events: list[RunEvent] = field(default_factory=list)

    async def emit(self, event: RunEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True)
class CompositeRunEventSink:
    sinks: tuple[RunEventSink, ...]

    async def emit(self, event: RunEvent) -> None:
        for sink in self.sinks:
            await emit_safely(sink, event)


async def emit_safely(sink: RunEventSink, event: RunEvent) -> None:
    """Emit telemetry without ever changing the user-facing run outcome."""

    try:
        await sink.emit(event)
    except Exception:
        logger.exception(
            "Run event sink failed",
            extra={"run_id": event.run_id, "event_type": event.event_type},
        )
