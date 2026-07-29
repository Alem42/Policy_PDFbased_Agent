from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.modules.chat.rag.agent.prompts import (
    get_agent_system_prompt,
    get_final_answer_system_prompt,
)
from app.modules.chat.rag.agent.state import AgentState
from app.modules.chat.rag.agent.tools import (
    ALL_TOOLS,
    import_web_page,
    prepare_final_answer,
    search_internal_documents,
)
from app.modules.chat.rag.checkpointer import get_checkpointer
from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target

logger = logging.getLogger(__name__)

# import_web_page is bound to the LLM only for admins — filtered at graph
# build/bind time, not just checked inside the tool, so a non-admin session
# never even sees it in the tool schema offered to the model.
NON_ADMIN_TOOLS = [t for t in ALL_TOOLS if t is not import_web_page]

# Document Analysis mode (answer_mode != "chat", including policymaker, which
# is always forced to "analysis") stays strictly document-grounded: only
# search_internal_documents is offered, so the model can only answer from the
# selected documents or say it can't — no full-corpus/web escalation, no
# import. That escalation belongs to Open Discussion mode, which already
# permits going beyond the selected documents (see agent/prompts.py).
ANALYSIS_MODE_TOOLS = [search_internal_documents, prepare_final_answer]

# Per user turn. Exhausted tools are removed from the next agent call's tool
# schema, so the model cannot keep selecting the same action indefinitely.
TOOL_CALL_LIMITS = {
    "search_internal_documents": 1,
    "search_full_corpus": 2,
    "ask_user": 1,
    "search_web": 2,
    "import_web_page": 1,
    "prepare_final_answer": 1,
}


def _tools_for(
    is_admin: bool,
    answer_mode: str,
    tool_call_counts: dict[str, int] | None = None,
) -> list:
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


async def agent_node(state: AgentState) -> dict:
    """The LLM turn: given the conversation + tool results so far, decide
    which tool action to take next."""
    response_mode = state.get("response_mode", "researcher")
    answer_mode = state.get("answer_mode", "analysis")
    is_admin = state.get("is_admin", False)

    provider, selected_model, _config = resolve_generation_target(state.get("model"))
    client = create_chat_client(provider, selected_model)
    available_tools = _tools_for(is_admin, answer_mode, state.get("tool_call_counts"))
    if not available_tools:
        raise RuntimeError("The agent has exhausted every available tool action.")
    llm_with_tools = client.bind_tools(
        available_tools,
        tool_choice="required",
        parallel_tool_calls=False,
    )

    system_prompt = get_agent_system_prompt(response_mode, answer_mode, is_admin=is_admin)
    messages = [SystemMessage(content=system_prompt), *state["messages"]]

    allowed_tool_names = {tool.name for tool in available_tools}
    for _attempt in range(3):
        response: AIMessage = await llm_with_tools.ainvoke(messages)
        if not response.tool_calls:
            raise RuntimeError("The agent did not choose a required tool action.")
        if len(response.tool_calls) > 1:
            logger.warning(
                "Model returned %s tool calls despite parallel_tool_calls=False; keeping only %s.",
                len(response.tool_calls),
                response.tool_calls[0].get("name"),
            )
            response.tool_calls = response.tool_calls[:1]

        selected_call = response.tool_calls[0]
        selected_tool = selected_call.get("name")
        if selected_tool in allowed_tool_names:
            return {"messages": [response], "resolved_model": f"{provider}/{selected_model}"}

        logger.warning(
            "Agent selected unavailable tool %r; returning an observation and retrying.",
            selected_tool,
        )
        recommended = [
            name
            for name in ("ask_user", "prepare_final_answer", "search_web")
            if name in allowed_tool_names
        ]
        messages.extend(
            [
                response,
                ToolMessage(
                    content=json.dumps(
                        {
                            "error": f"The {selected_tool} action is no longer available.",
                            "reason": "Its per-turn call budget has been exhausted.",
                            "choose_instead": recommended,
                        }
                    ),
                    tool_call_id=selected_call["id"],
                    name=selected_tool or "unavailable_tool",
                ),
            ]
        )

    raise RuntimeError("The agent repeatedly selected an unavailable tool action.")


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "record_tool_call"
    raise RuntimeError("The agent produced no tool call.")


def record_tool_call_node(state: AgentState) -> dict:
    """Count the single accepted action before ToolNode executes it."""
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", None) or []
    if len(calls) != 1:
        raise RuntimeError("Exactly one tool call is required per ReAct turn.")
    tool_name = calls[0]["name"]
    counts = dict(state.get("tool_call_counts", {}))
    counts[tool_name] = counts.get(tool_name, 0) + 1
    return {"tool_call_counts": counts}


def route_after_tools(state: AgentState) -> str:
    """The prepare tool is the only exit from the ReAct action loop."""
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and last.name == "prepare_final_answer":
        return "final_generation"
    return "agent"


async def final_generation_node(state: AgentState) -> dict:
    """Write the final answer without tools so its content streams normally."""
    response_mode = state.get("response_mode", "researcher")
    answer_mode = state.get("answer_mode", "analysis")
    provider, selected_model, _config = resolve_generation_target(state.get("model"))
    client = create_chat_client(provider, selected_model)
    system_prompt = get_final_answer_system_prompt(response_mode, answer_mode)
    messages = [SystemMessage(content=system_prompt), *state["messages"]]

    response: AIMessage = await client.ainvoke(messages)
    return {"messages": [response], "resolved_model": f"{provider}/{selected_model}"}


def build_agent_graph():
    """Compile the ReAct-style web-search agent loop: agent_node <-> tools_node.

    Distinct from build_pdf_qa_graph() (the classic linear 5-node RAG graph,
    still used by /chat and unaffected by this): here the LLM itself decides,
    turn by turn, which tool to call next — there is no fixed node sequence.
    Compiled with the persistent Postgres checkpointer so `interrupt()` inside
    ask_user/import_web_page can suspend and later resume via
    Command(resume=...) against the same thread_id.
    """
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("record_tool_call", record_tool_call_node)
    builder.add_node("tools", ToolNode(ALL_TOOLS))
    builder.add_node("final_generation", final_generation_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_after_agent, {"record_tool_call": "record_tool_call"}
    )
    builder.add_edge("record_tool_call", "tools")
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {"agent": "agent", "final_generation": "final_generation"},
    )
    builder.add_edge("final_generation", END)
    return builder.compile(checkpointer=get_checkpointer())


_agent_graph = None


def get_agent_graph():
    """Lazily build+compile the agent graph on first use.

    Must not compile at import time: compile() binds the checkpointer, which
    is only opened once the FastAPI lifespan has run (see checkpointer.py).
    """
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
