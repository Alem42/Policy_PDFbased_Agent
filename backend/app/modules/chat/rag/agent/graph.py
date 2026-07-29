from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.modules.chat.rag.agent.prompts import get_agent_system_prompt
from app.modules.chat.rag.agent.state import AgentState
from app.modules.chat.rag.agent.tools import ALL_TOOLS, import_web_page
from app.modules.chat.rag.checkpointer import get_checkpointer
from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target

# import_web_page is bound to the LLM only for admins — filtered at graph
# build/bind time, not just checked inside the tool, so a non-admin session
# never even sees it in the tool schema offered to the model.
NON_ADMIN_TOOLS = [t for t in ALL_TOOLS if t is not import_web_page]


def _tools_for(is_admin: bool) -> list:
    return ALL_TOOLS if is_admin else NON_ADMIN_TOOLS


async def agent_node(state: AgentState) -> dict:
    """The LLM turn: given the conversation + tool results so far, decide
    whether to call another tool or write the final answer."""
    response_mode = state.get("response_mode", "researcher")
    answer_mode = state.get("answer_mode", "analysis")
    is_admin = state.get("is_admin", False)

    provider, selected_model, _config = resolve_generation_target(state.get("model"))
    client = create_chat_client(provider, selected_model)
    llm_with_tools = client.bind_tools(_tools_for(is_admin))

    system_prompt = get_agent_system_prompt(response_mode, answer_mode, is_admin=is_admin)
    messages = [SystemMessage(content=system_prompt), *state["messages"]]

    response: AIMessage = await llm_with_tools.ainvoke(messages)
    return {"messages": [response], "resolved_model": f"{provider}/{selected_model}"}


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


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
    builder.add_node("tools", ToolNode(ALL_TOOLS))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
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
