from dataclasses import dataclass


@dataclass(frozen=True)
class StartTurnRequest:
    """Framework-independent inputs for starting a persisted chat turn."""

    user_id: str
    question: str
    identifiers: tuple[str, ...]
    response_mode: str
    agent_mode: str
    session_id: str | None = None
    create_pending_assistant: bool = False


@dataclass(frozen=True)
class StartedTurn:
    """Session context prepared before an orchestrator runs."""

    session_id: str
    user_id: str
    history: list[dict]
    assistant_message_id: str | None = None
