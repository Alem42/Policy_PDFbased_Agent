"""Tool visibility and per-turn budgets for the ReAct orchestrator."""

from app.modules.chat.rag.agent.tools import (
    ALL_TOOLS,
    import_web_page,
    prepare_final_answer,
    search_internal_documents,
)

NON_ADMIN_TOOLS = [tool for tool in ALL_TOOLS if tool is not import_web_page]
ANALYSIS_MODE_TOOLS = [search_internal_documents, prepare_final_answer]

TOOL_CALL_LIMITS = {
    "search_internal_documents": 5,
    "search_full_corpus": 5,
    "ask_user": 20,
    "search_web": 4,
    "import_web_page": 1,
    "prepare_final_answer": 1,
}

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
    return [
        tool
        for tool in available
        if counts.get(tool.name, 0) < TOOL_CALL_LIMITS.get(tool.name, 1)
    ]
