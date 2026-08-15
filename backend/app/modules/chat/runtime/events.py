"""Provider-neutral event contracts for agent runs, evals, and audit trails."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

RunEventType = Literal[
    "run_started",
    "model_call_started",
    "model_call_finished",
    "tool_call_started",
    "tool_call_finished",
    "first_token",
    "run_finished",
    "run_failed",
]
RunStatus = Literal["started", "succeeded", "failed"]

# Metadata is intentionally allowlisted. Raw prompts, model messages, tool
# arguments, headers, URLs with credentials, and private reasoning never enter
# the event contract.
PUBLIC_METADATA_KEYS = frozenset(
    {
        "agent_mode",
        "answer_mode",
        "citation_count",
        "evidence_sufficient",
        "model",
        "output_format",
        "response_mode",
        "result_count",
        "scope",
        "source_policy",
        "workflow_mode",
    }
)
TOKEN_USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_input_tokens",
    }
)


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    sequence: int
    event_type: RunEventType
    occurred_at: datetime
    node_name: str | None = None
    tool_name: str | None = None
    duration_ms: float | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    status: RunStatus | None = None
    error_type: str | None = None
    public_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Run event sequence must start at 1.")
        object.__setattr__(self, "token_usage", sanitize_token_usage(self.token_usage))
        object.__setattr__(
            self,
            "public_metadata",
            sanitize_public_metadata(self.public_metadata),
        )


class RunEventFactory:
    """Create monotonically sequenced events for one logical run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._sequence = 0

    def create(self, event_type: RunEventType, **kwargs: Any) -> RunEvent:
        self._sequence += 1
        return RunEvent(
            run_id=self.run_id,
            sequence=self._sequence,
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            **kwargs,
        )


def sanitize_public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep only explicit, scalar fields approved for logs and persistence."""

    return {
        key: value
        for key, value in metadata.items()
        if key in PUBLIC_METADATA_KEYS and _is_public_scalar(value)
    }


def sanitize_token_usage(token_usage: dict[str, Any]) -> dict[str, int]:
    return {
        key: value
        for key, value in token_usage.items()
        if key in TOKEN_USAGE_KEYS and isinstance(value, int) and value >= 0
    }


def _is_public_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
