from __future__ import annotations

from app.modules.chat.domain.modes import ChatExecutionProfile
from app.modules.chat.runtime.context import build_agent_run_context
from app.modules.chat.runtime.events import RunEventFactory
from app.modules.chat.runtime.postgres_sink import PostgresRunEventSink


def _context():
    return build_agent_run_context(
        run_id="run-1",
        session_id="session-1",
        assistant_message_id="message-1",
        user_id="user-1",
        is_admin=False,
        profile=ChatExecutionProfile("research", "selected_only", "adaptive"),
        model="provider/model",
        configuration={"top_k": 8},
    )


async def test_postgres_sink_ensures_run_once_and_appends_every_event() -> None:
    class RecordingRepository:
        def __init__(self) -> None:
            self.contexts = []
            self.events = []

        def ensure_run(self, context) -> None:
            self.contexts.append(context)

        def append_event(self, event) -> int:
            self.events.append(event)
            return len(self.events)

    repository = RecordingRepository()
    context = _context()
    sink = PostgresRunEventSink(context, repository)
    factory = RunEventFactory(context.run_id)

    await sink.emit(factory.create("run_started"))
    await sink.emit(factory.create("run_finished"))

    assert repository.contexts == [context]
    assert [event.event_type for event in repository.events] == [
        "run_started",
        "run_finished",
    ]


async def test_postgres_sink_rejects_an_event_for_another_run() -> None:
    class UnusedRepository:
        def ensure_run(self, context) -> None:
            raise AssertionError("must not persist")

        def append_event(self, event) -> int:
            raise AssertionError("must not persist")

    sink = PostgresRunEventSink(_context(), UnusedRepository())
    event = RunEventFactory("another-run").create("run_started")

    try:
        await sink.emit(event)
    except ValueError as exc:
        assert "run_id" in str(exc)
    else:
        raise AssertionError("Mismatched run_id should be rejected")
