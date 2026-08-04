"""Tool visibility and per-turn budgets for the ReAct orchestrator."""

from app.modules.chat.agent_limits.config import AgentToolLimitsConfig
from app.modules.chat.agent_limits.service import active_config as active_tool_limits
from app.modules.chat.rag.agent.tools import (
    ALL_TOOLS,
    import_web_page,
    prepare_final_answer,
    search_internal_documents,
)

NON_ADMIN_TOOLS = [tool for tool in ALL_TOOLS if tool is not import_web_page]
ANALYSIS_MODE_TOOLS = [search_internal_documents, prepare_final_answer]

# Defaults -- also the fallback used until an admin overrides them via
# Manage > Agent tool limits (see chat.agent_limits), or when the
# agent_tool_limit_settings row is absent.
TOOL_CALL_LIMITS = AgentToolLimitsConfig().as_limits()

EVIDENCE_TIER_TOOLS = {"search_internal_documents", "search_full_corpus", "search_web"}


def tools_for(
    is_admin: bool,
    answer_mode: str,
    tool_call_counts: dict[str, int] | None = None,
) -> list:
    """Return only tools allowed by mode, role, and remaining budget."""

    if answer_mode != "chat":
        available = ANALYSIS_MODE_TOOLS
    else:
        available = ALL_TOOLS if is_admin else NON_ADMIN_TOOLS
    counts = tool_call_counts or {}
    limits = active_tool_limits().as_limits()
    return [
        tool
        for tool in available
        if counts.get(tool.name, 0) < limits.get(tool.name, 1)
    ]
