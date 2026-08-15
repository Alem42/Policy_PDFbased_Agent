from __future__ import annotations

from app.modules.chat.domain.modes import ChatExecutionProfile
from app.modules.chat.runtime.context import AgentRunContext, build_agent_run_context
from app.modules.chat.runtime.versioning import PROMPT_VERSION, stable_configuration_version


def _profile() -> ChatExecutionProfile:
    return ChatExecutionProfile(
        workflow_mode="research",
        source_policy="selected_only",
        output_format="adaptive",
    )


def test_configuration_version_is_stable_across_mapping_order() -> None:
    first = stable_configuration_version(
        {"top_k": 8, "limits": {"web": 2, "library": 1}}
    )
    second = stable_configuration_version(
        {"limits": {"library": 1, "web": 2}, "top_k": 8}
    )

    assert first == second
    assert first.startswith("sha256:")


def test_configuration_version_changes_with_behavior() -> None:
    selected = stable_configuration_version({"source_policy": "selected_only"})
    web = stable_configuration_version({"source_policy": "web_with_approval"})

    assert selected != web


def test_configuration_version_excludes_secret_values() -> None:
    first = stable_configuration_version({"top_k": 8, "api_key": "first-secret"})
    second = stable_configuration_version({"api_key": "second-secret", "top_k": 8})

    assert first == second


def test_run_context_round_trip_preserves_run_id_for_resume() -> None:
    context = build_agent_run_context(
        run_id="assistant-message-1",
        session_id="session-1",
        assistant_message_id="assistant-message-1",
        user_id="user-1",
        is_admin=False,
        profile=_profile(),
        model="provider/model",
        configuration={"top_k": 8, "source_policy": "selected_only"},
    )

    resumed_context = AgentRunContext.from_dict(context.as_dict())

    assert resumed_context == context
    assert resumed_context.run_id == "assistant-message-1"
    assert resumed_context.prompt_version == PROMPT_VERSION


def test_new_requests_receive_distinct_run_ids() -> None:
    common = {
        "session_id": "session-1",
        "assistant_message_id": None,
        "user_id": "user-1",
        "is_admin": False,
        "profile": _profile(),
        "model": None,
        "configuration": {"top_k": 8},
    }

    assert build_agent_run_context(**common).run_id != build_agent_run_context(**common).run_id
