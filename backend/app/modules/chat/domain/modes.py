"""Canonical chat execution dimensions and legacy compatibility mapping.

The current public API still exposes response/answer/agent modes.  This module
defines their future replacement without changing any request or persistence
contracts yet.  Keeping the conversion pure makes it safe to reuse from HTTP,
LangGraph, evaluation, and future MCP adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

WorkflowMode = Literal["quick_answer", "research", "deep_research"]
SourcePolicy = Literal["selected_only", "library_allowed", "web_with_approval"]
OutputFormat = Literal["adaptive", "policy_brief"]

_LEGACY_RESPONSE_MODES = {"researcher", "policymaker", "student"}
_LEGACY_ANSWER_MODES = {"analysis", "chat"}
_LEGACY_AGENT_MODES = {"direct", "react"}


class InvalidLegacyProfileError(ValueError):
    """Raised when a legacy mode value cannot be mapped safely."""


@dataclass(frozen=True)
class ChatExecutionProfile:
    """Orthogonal execution, source-boundary, and presentation choices."""

    workflow_mode: WorkflowMode
    source_policy: SourcePolicy
    output_format: OutputFormat


def profile_from_legacy(
    response_mode: str,
    answer_mode: str,
    agent_mode: str,
) -> ChatExecutionProfile:
    """Map an existing request/session mode tuple to its canonical profile.

    This is intentionally a compatibility description, not a new router.  It
    performs no I/O and does not change the behavior of existing endpoints.
    Policymaker remains selected-document grounded and becomes a policy-brief
    presentation. The retired Student value remains accepted only so migration
    and historical-data adapters can map it to the canonical adaptive profile.
    """

    _validate_legacy_value("response_mode", response_mode, _LEGACY_RESPONSE_MODES)
    _validate_legacy_value("answer_mode", answer_mode, _LEGACY_ANSWER_MODES)
    _validate_legacy_value("agent_mode", agent_mode, _LEGACY_AGENT_MODES)

    if response_mode == "policymaker":
        return ChatExecutionProfile(
            workflow_mode="research",
            source_policy="selected_only",
            output_format="policy_brief",
        )

    workflow_mode: WorkflowMode = "quick_answer" if agent_mode == "direct" else "research"
    source_policy: SourcePolicy = (
        "web_with_approval" if answer_mode == "chat" else "selected_only"
    )
    return ChatExecutionProfile(
        workflow_mode=workflow_mode,
        source_policy=source_policy,
        output_format="adaptive",
    )


def _validate_legacy_value(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise InvalidLegacyProfileError(f"Unknown {name} {value!r}; expected one of: {choices}.")


def workflow_mode(value: str) -> WorkflowMode:
    """Validate a canonical workflow value at non-Pydantic boundaries."""

    if value not in {"quick_answer", "research", "deep_research"}:
        raise ValueError(f"Unknown workflow mode: {value!r}.")
    return cast(WorkflowMode, value)
