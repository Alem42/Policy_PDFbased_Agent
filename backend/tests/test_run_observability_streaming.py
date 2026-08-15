from __future__ import annotations

from types import SimpleNamespace

from langgraph.types import Command

from app.modules.chat.application import streaming
from app.modules.chat.domain.modes import ChatExecutionProfile
from app.modules.chat.runtime.context import build_agent_run_context
from app.modules.chat.runtime.sink import InMemoryRunEventSink


def _context(agent_mode: str = "direct"):
    return build_agent_run_context(
        run_id="run-1",
        session_id="session-1",
        assistant_message_id="message-1",
        user_id="user-1",
        is_admin=False,
        profile=ChatExecutionProfile("research", "selected_only", "adaptive"),
        model="provider/model",
        configuration={"top_k": 8, "agent_mode": agent_mode},
    )


async def test_direct_stream_emits_complete_observability_trace(monkeypatch) -> None:
    monkeypatch.setattr(
        streaming.direct_orchestrator,
        "retrieve",
        lambda **kwargs: {
            "citations": [{"document_id": "doc-1", "quote": "Evidence"}],
            "context": "Evidence",
            "evidence_sufficient": True,
        },
    )
    monkeypatch.setattr(
        streaming,
        "resolve_generation_target",
        lambda model: ("provider", "model", {}),
    )

    async def answer_stream(**kwargs):
        yield "Grounded answer"

    async def no_suggestions(**kwargs):
        if False:
            yield ""

    async def no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(streaming, "generate_answer_streaming", answer_stream)
    monkeypatch.setattr(streaming, "stream_suggestion_events", no_suggestions)
    monkeypatch.setattr(streaming.chat_turn_service, "finalize_message", no_op)
    monkeypatch.setattr(streaming.chat_turn_service, "touch", no_op)

    sink = InMemoryRunEventSink()
    response_events = [
        event
        async for event in streaming.stream_direct_events(
            question="Question",
            document_ids=["doc-1"],
            filenames=None,
            model="provider/model",
            response_mode="researcher",
            answer_mode="analysis",
            top_k=8,
            include_restricted=False,
            history=[],
            session_id="session-1",
            assistant_message_id="message-1",
            run_context=_context(),
            event_sink=sink,
        )
    ]

    assert response_events
    assert [event.event_type for event in sink.events] == [
        "run_started",
        "tool_call_started",
        "tool_call_finished",
        "model_call_started",
        "first_token",
        "model_call_finished",
        "run_finished",
    ]
    assert sink.events[-1].public_metadata["citation_count"] == 1


async def test_react_resume_does_not_emit_duplicate_run_started(monkeypatch) -> None:
    class InterruptingGraph:
        async def astream(self, graph_input, *, config, stream_mode):
            yield "updates", {
                "__interrupt__": (SimpleNamespace(value={"type": "ask_user"}),)
            }

    async def message_steps(_message_id):
        return []

    monkeypatch.setattr(streaming.react_orchestrator, "graph", lambda: InterruptingGraph())
    monkeypatch.setattr(streaming.chat_turn_service, "message_steps", message_steps)
    sink = InMemoryRunEventSink()

    events = streaming.stream_agent_events(
        Command(resume="continue"),
        config={"configurable": {"thread_id": "session-1"}},
        session_id="session-1",
        response_mode="researcher",
        answer_mode="analysis",
        assistant_message_id="message-1",
        run_context=_context("react"),
        event_sink=sink,
    )
    await anext(events)
    await events.aclose()

    assert "run_started" not in [event.event_type for event in sink.events]
    assert sink.events[0].event_type == "model_call_started"
