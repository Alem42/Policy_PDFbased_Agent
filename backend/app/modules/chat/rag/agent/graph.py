from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.modules.chat.rag.agent.policy import (
    EVIDENCE_TIER_TOOLS,
    NON_ADMIN_TOOLS,
    TOOL_CALL_LIMITS,
    tools_for,
)
from app.modules.chat.rag.agent.prompts import (
    get_agent_system_prompt,
    get_final_answer_system_prompt,
)
from app.modules.chat.rag.agent.state import AgentState
from app.modules.chat.rag.agent.tools import (
    ALL_TOOLS,
)
from app.modules.chat.rag.checkpointer import get_checkpointer
from app.modules.chat.rag.generation import create_chat_client, resolve_generation_target
from app.modules.chat.rag.prompts import get_insufficient_evidence_message

logger = logging.getLogger(__name__)

__all__ = ["NON_ADMIN_TOOLS", "TOOL_CALL_LIMITS"]

_tools_for = tools_for

# DISABLED (2026-08-01) at the user's request while testing: skipping the
# model's own turn also skips the visible "Preparing the final answer…" trace
# step (auto_finalize_node bypasses record_tool_call/tools, the two nodes
# router.py turns into tool_call/tool_result SSE events), which made it look
# like the agent had stopped calling prepare_final_answer at all. Flip back
# to True to re-enable — _should_auto_finalize/auto_finalize_node below are
# untouched, only route_after_tools' use of them is gated.
AUTO_FINALIZE_ENABLED = False

# --- TEMPORARY code-level backstop -----------------------------------------
# Prompt wording alone (see AGENT_STRATEGY_PROMPT / SUFFICIENT_EVIDENCE_REMINDER
# in prompts.py / tools.py) does not reliably stop some models from
# re-searching "for more detail" even when evidence_sufficient=true —
# verified against deepseek-chat, the default provider (DEFAULT_PROVIDER in
# llm_providers.py). Rather than trust the model's own stop/continue
# judgement on the very first sufficient result, skip its turn outright and
# finalize immediately.
#
# This trusts evidence_sufficient at face value with no topical/entity check
# of its own. assess_evidence_sufficiency() (see evidence.py) is planned to
# become keyword/entity-aware itself, at which point evidence_sufficient=true
# will already mean "and it covers what the question named" — an earlier
# version of this function additionally cross-checked question entities
# against the retrieved text in Python, which became redundant work once
# that lands there instead, so it was deliberately dropped here. Until the
# keyword-aware gate ships, this can auto-finalize on evidence that is
# topically close but silent on a specific country/org/date the question
# named (e.g. EU-level content answering a Germany-specific question) — a
# known, accepted gap, not an oversight.
_AUTO_FINALIZE_ANSWER_PLAN = (
    "Answer using the evidence already retrieved this turn — the retrieval "
    "gate already confirmed it covers the question."
)

# Mirrors the "compare/verify against the web" exception in
# AGENT_STRATEGY_PROMPT: that flow deliberately calls a search tool even
# after an earlier tier was already sufficient, so the backstop must not
# short-circuit before the model gets to run that intentional second call.
_COMPARISON_TRIGGER_WORDS = (
    "对比",
    "比对",
    "核实",
    "核对",
    "compare",
    "cross-check",
    "cross check",
    "verify",
    "up to date",
    "up-to-date",
    "still accurate",
    "still current",
)


def _should_auto_finalize(state: AgentState) -> bool:
    """True if the just-received tool result is the first sufficient
    evidence-tier result this turn, in Open Discussion mode, for a question
    that isn't asking for a web comparison."""
    if state.get("answer_mode", "analysis") != "chat":
        return False
    last = state["messages"][-1]
    if not (isinstance(last, ToolMessage) and last.name in EVIDENCE_TIER_TOOLS):
        return False
    try:
        payload = json.loads(last.content)
    except (TypeError, ValueError):
        return False
    if not payload.get("evidence_sufficient"):
        return False

    counts = state.get("tool_call_counts", {})
    search_calls_this_turn = sum(counts.get(name, 0) for name in EVIDENCE_TIER_TOOLS)
    if search_calls_this_turn != 1:
        # Only short-circuit the very first search of the turn. If the model
        # already chose to escalate past that, let its own loop play out
        # rather than second-guessing a decision already in flight.
        return False

    question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )
    question = question if isinstance(question, str) else str(question)
    return not any(word in question.lower() for word in _COMPARISON_TRIGGER_WORDS)


def auto_finalize_node(state: AgentState) -> dict:
    """TEMPORARY: synthesize the prepare_final_answer step the model would
    presumably have taken anyway, instead of giving it another turn to
    second-guess sufficient evidence (see _should_auto_finalize above). The
    synthetic messages keep final_generation_node's input shape identical to
    the normal path — it always expects the transcript to end with a
    prepare_final_answer tool result."""
    citations = state.get("citations", [])
    numbers = sorted({c["number"] for c in citations if isinstance(c.get("number"), int)})
    call_id = f"auto-finalize-{len(state['messages'])}"
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "prepare_final_answer",
                        "args": {
                            "answer_plan": _AUTO_FINALIZE_ANSWER_PLAN,
                            "citation_numbers": numbers,
                        },
                        "id": call_id,
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "ready": True,
                        "answer_plan": _AUTO_FINALIZE_ANSWER_PLAN,
                        "citation_numbers": numbers,
                        "auto_finalized": True,
                    }
                ),
                tool_call_id=call_id,
                name="prepare_final_answer",
            ),
        ]
    }


# --- end TEMPORARY code-level backstop --------------------------------------


def _messages_for_current_turn(messages: list) -> list:
    """Hide prior turns' internal tool traces from the current ReAct loop.

    The checkpoint intentionally keeps the whole conversation, including old
    ToolMessages. Those observations may say that a per-turn budget was
    exhausted, which is no longer true after the user asks a new question.
    Preserve prior conversational Human/AI messages, but expose tool calls
    and ToolMessages only from the latest user question onward.
    """
    latest_human_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        None,
    )
    if latest_human_index is None:
        return list(messages)

    conversational_history = [
        message
        for message in messages[:latest_human_index]
        if isinstance(message, HumanMessage)
        or (
            isinstance(message, AIMessage)
            and not message.tool_calls
            and bool(message.content)
        )
    ]
    return [*conversational_history, *messages[latest_human_index:]]


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
    messages = [
        SystemMessage(content=system_prompt),
        *_messages_for_current_turn(state["messages"]),
    ]

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
    tool_args = dict(calls[0].get("args") or {})
    counts = dict(state.get("tool_call_counts", {}))
    counts[tool_name] = counts.get(tool_name, 0) + 1
    # Tokens spent on the single agent_node LLM call that decided to take
    # THIS action — usage_metadata is populated by the provider on the
    # AIMessage itself (langchain_core standard field), None if it didn't
    # report usage. Not the tool's own cost (the tools here don't call an
    # LLM directly) — this is "what did it cost to decide on this step."
    usage = getattr(last, "usage_metadata", None)
    tokens_used = usage.get("total_tokens") if usage else None
    return {
        "tool_call_counts": counts,
        "last_tool_call": {
            "tool": tool_name,
            "query": tool_args.get("query"),
            "decision_reason": tool_args.get("decision_reason"),
            "question": tool_args.get("question"),
            "url": tool_args.get("url"),
            "title": tool_args.get("title"),
            # Belongs to the PREVIOUS step, not this one — router.py attaches
            # it there rather than storing it on this new step (see
            # REFLECTION_FIELD_RULE in prompts.py).
            "reflection_on_previous_result": tool_args.get("reflection_on_previous_result"),
            "tokens_used": tokens_used,
        },
    }


def route_after_tools(state: AgentState) -> str:
    """The prepare tool is the only exit from the ReAct action loop.

    Document Analysis mode has no full-corpus/web escalation (see
    ANALYSIS_MODE_TOOLS) — search_internal_documents is its only evidence
    tier, so if that never became sufficient this turn, the answer must be a
    deterministic refusal identical to the Direct/linear graph's
    (insufficient_evidence_node in rag/graph/nodes.py), not an LLM-written
    one. Open Discussion mode keeps its existing general-knowledge fallback
    inside AGENT_STRATEGY_PROMPT/final_generation, since evidence_sources can
    legitimately stay empty there while the model still answers.
    """
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and last.name == "prepare_final_answer":
        if state.get("answer_mode", "analysis") != "chat" and not state.get("evidence_sources"):
            return "insufficient_evidence"
        return "final_generation"
    if AUTO_FINALIZE_ENABLED and _should_auto_finalize(state):
        return "auto_finalize"
    return "agent"


def insufficient_evidence_node(state: AgentState) -> dict:
    """Document Analysis mode, no tier ever produced sufficient evidence:
    return the same mode-aware templated refusal the Direct/linear graph
    uses (see rag/graph/nodes.py::insufficient_evidence_node), instead of
    letting the LLM writer improvise wording for it.
    """
    question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )
    reason = state.get("last_evidence_reason") or "The retrieved excerpts are too weak."
    message = get_insufficient_evidence_message(
        question=question,
        reason=reason,
        mode=state.get("response_mode", "researcher"),
    )
    return {"messages": [AIMessage(content=message)]}


async def final_generation_node(state: AgentState) -> dict:
    """Write the final answer without tools so its content streams normally."""
    response_mode = state.get("response_mode", "researcher")
    answer_mode = state.get("answer_mode", "analysis")
    provider, selected_model, _config = resolve_generation_target(state.get("model"))
    client = create_chat_client(provider, selected_model)
    system_prompt = get_final_answer_system_prompt(response_mode, answer_mode)
    messages = [
        SystemMessage(content=system_prompt),
        *_messages_for_current_turn(state["messages"]),
    ]

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
    builder.add_node("insufficient_evidence", insufficient_evidence_node)
    builder.add_node("auto_finalize", auto_finalize_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_after_agent, {"record_tool_call": "record_tool_call"}
    )
    builder.add_edge("record_tool_call", "tools")
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "agent": "agent",
            "final_generation": "final_generation",
            "insufficient_evidence": "insufficient_evidence",
            "auto_finalize": "auto_finalize",
        },
    )
    builder.add_edge("final_generation", END)
    builder.add_edge("insufficient_evidence", END)
    builder.add_edge("auto_finalize", "final_generation")
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
