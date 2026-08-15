"""Identity and reproducibility metadata for one logical agent run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from app.modules.chat.domain.modes import ChatExecutionProfile
from app.modules.chat.runtime.versioning import PROMPT_VERSION, stable_configuration_version


@dataclass(frozen=True)
class AgentRunContext:
    """Immutable metadata shared by Direct, ReAct, evaluation, and telemetry."""

    run_id: str
    session_id: str
    assistant_message_id: str | None
    user_id: str
    is_admin: bool
    profile: ChatExecutionProfile
    model: str | None
    prompt_version: str
    configuration_version: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentRunContext:
        data = dict(value)
        data["profile"] = ChatExecutionProfile(**data["profile"])
        return cls(**data)


def build_agent_run_context(
    *,
    session_id: str,
    assistant_message_id: str | None,
    user_id: str,
    is_admin: bool,
    profile: ChatExecutionProfile,
    model: str | None,
    configuration: dict[str, Any],
    run_id: str | None = None,
) -> AgentRunContext:
    """Build a new run context, or preserve ``run_id`` when resuming a run."""

    return AgentRunContext(
        run_id=run_id or str(uuid4()),
        session_id=session_id,
        assistant_message_id=assistant_message_id,
        user_id=user_id,
        is_admin=is_admin,
        profile=profile,
        model=model,
        prompt_version=PROMPT_VERSION,
        configuration_version=stable_configuration_version(configuration),
    )
