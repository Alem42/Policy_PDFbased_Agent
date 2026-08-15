"""Tool visibility and per-turn budgets for the ReAct orchestrator."""

from app.modules.chat.agent_limits.config import AgentToolLimitsConfig
from app.modules.chat.agent_limits.service import active_config as active_tool_limits
from app.modules.chat.rag.agent.tools import (
    ALL_TOOLS,
    import_web_page,
    prepare_final_answer,
    search_full_corpus,
    search_internal_documents,
)

NON_ADMIN_TOOLS = [tool for tool in ALL_TOOLS if tool is not import_web_page]
ANALYSIS_MODE_TOOLS = [search_internal_documents, prepare_final_answer]
LIBRARY_MODE_TOOLS = [
    search_internal_documents,
    search_full_corpus,
    prepare_final_answer,
]

# Defaults -- also the fallback used until an admin overrides them via
# Manage > Agent tool limits (see chat.agent_limits), or when the
# agent_tool_limit_settings row is absent.
TOOL_CALL_LIMITS = AgentToolLimitsConfig().as_limits()

EVIDENCE_TIER_TOOLS = {"search_internal_documents", "search_full_corpus", "search_web"}


def tools_for(
    is_admin: bool,
    answer_mode: str,
    tool_call_counts: dict[str, int] | None = None,
    *,
    limits: dict[str, int] | None = None,
    source_policy: str | None = None,
) -> list:
    """Return tools allowed by source boundary, role, and remaining budget.

    ``source_policy`` is the canonical contract. ``answer_mode`` remains the
    compatibility fallback until API and persisted-session migration happens.
    Presentation/output format is deliberately absent from this decision.
    """

    if source_policy == "selected_only" or (
        source_policy is None and answer_mode != "chat"
    ):
        available = ANALYSIS_MODE_TOOLS
    elif source_policy == "library_allowed":
        available = LIBRARY_MODE_TOOLS
    else:
        available = ALL_TOOLS if is_admin else NON_ADMIN_TOOLS
    counts = tool_call_counts or {}
    effective_limits = limits if limits is not None else active_limits()
    return [
        tool for tool in available if counts.get(tool.name, 0) < effective_limits.get(tool.name, 1)
    ]


def active_limits() -> dict[str, int]:
    """Return the persisted per-tool budgets currently enforced by the agent."""

    return active_tool_limits().as_limits()
