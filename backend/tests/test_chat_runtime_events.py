from __future__ import annotations

from app.modules.chat.runtime.events import RunEventFactory
from app.modules.chat.runtime.sink import (
    CompositeRunEventSink,
    InMemoryRunEventSink,
    emit_safely,
)


def test_event_factory_produces_stable_sequence() -> None:
    factory = RunEventFactory("run-1")

    events = [
        factory.create("run_started", status="started"),
        factory.create("tool_call_started", tool_name="policy_search"),
        factory.create("run_finished", status="succeeded", duration_ms=12.5),
    ]

    assert [event.sequence for event in events] == [1, 2, 3]
    assert {event.run_id for event in events} == {"run-1"}


def test_event_removes_secrets_and_non_allowlisted_tool_arguments() -> None:
    event = RunEventFactory("run-1").create(
        "tool_call_started",
        tool_name="policy_search",
        public_metadata={
            "scope": "selected",
            "result_count": 3,
            "api_key": "must-not-survive",
            "authorization": "Bearer must-not-survive",
            "question": "private user text",
            "tool_arguments": {"database_url": "must-not-survive"},
        },
        token_usage={
            "input_tokens": 10,
            "total_tokens": 12,
            "raw_response": "must-not-survive",
        },
    )

    assert event.public_metadata == {"scope": "selected", "result_count": 3}
    assert event.token_usage == {"input_tokens": 10, "total_tokens": 12}
    assert "must-not-survive" not in repr(event)


async def test_sink_failure_does_not_interrupt_event_delivery() -> None:
    class FailingSink:
        async def emit(self, event) -> None:
            raise RuntimeError("telemetry is unavailable")

    event = RunEventFactory("run-1").create("run_started")

    await emit_safely(FailingSink(), event)


async def test_composite_sink_continues_after_one_sink_fails() -> None:
    class FailingSink:
        async def emit(self, event) -> None:
            raise RuntimeError("telemetry is unavailable")

    memory = InMemoryRunEventSink()
    composite = CompositeRunEventSink((FailingSink(), memory))
    event = RunEventFactory("run-1").create("run_finished")

    await composite.emit(event)

    assert memory.events == [event]
