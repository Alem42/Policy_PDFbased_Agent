import pytest

from app.modules.chat.domain.modes import (
    ChatExecutionProfile,
    InvalidLegacyProfileError,
    profile_from_legacy,
)


@pytest.mark.parametrize(
    ("response_mode", "answer_mode", "agent_mode", "expected"),
    [
        (
            "researcher",
            "analysis",
            "direct",
            ChatExecutionProfile("quick_answer", "selected_only", "adaptive"),
        ),
        (
            "researcher",
            "analysis",
            "react",
            ChatExecutionProfile("research", "selected_only", "adaptive"),
        ),
        (
            "researcher",
            "chat",
            "react",
            ChatExecutionProfile("research", "web_with_approval", "adaptive"),
        ),
        (
            "researcher",
            "chat",
            "direct",
            ChatExecutionProfile("quick_answer", "web_with_approval", "adaptive"),
        ),
        (
            "policymaker",
            "analysis",
            "react",
            ChatExecutionProfile("research", "selected_only", "policy_brief"),
        ),
        (
            "policymaker",
            "chat",
            "direct",
            ChatExecutionProfile("research", "selected_only", "policy_brief"),
        ),
    ],
)
def test_profile_from_legacy_maps_existing_modes(
    response_mode: str,
    answer_mode: str,
    agent_mode: str,
    expected: ChatExecutionProfile,
) -> None:
    assert profile_from_legacy(response_mode, answer_mode, agent_mode) == expected


@pytest.mark.parametrize(
    ("response_mode", "answer_mode", "agent_mode", "invalid_field"),
    [
        ("expert", "analysis", "react", "response_mode"),
        ("researcher", "browse", "react", "answer_mode"),
        ("researcher", "analysis", "supervisor", "agent_mode"),
    ],
)
def test_profile_from_legacy_rejects_unknown_values(
    response_mode: str,
    answer_mode: str,
    agent_mode: str,
    invalid_field: str,
) -> None:
    with pytest.raises(InvalidLegacyProfileError, match=invalid_field):
        profile_from_legacy(response_mode, answer_mode, agent_mode)


def test_output_format_does_not_change_source_policy() -> None:
    researcher = profile_from_legacy("researcher", "analysis", "react")
    policymaker = profile_from_legacy("policymaker", "analysis", "react")

    assert researcher.source_policy == policymaker.source_policy == "selected_only"
    assert researcher.output_format != policymaker.output_format


def test_retired_student_value_maps_only_for_legacy_migration() -> None:
    assert profile_from_legacy("student", "analysis", "react") == ChatExecutionProfile(
        "research", "selected_only", "adaptive"
    )
