"""Streaming application drivers for Direct and ReAct chat turns.

The HTTP router owns request validation and ``StreamingResponse`` creation.
This module owns execution, persistence, and translation of domain/graph
events into the stable SSE protocol consumed by the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.core.ai.token_usage import aggregate_turn_token_usage
from app.modules.chat.api.sse import (
    apply_tool_result,
    encode_sse,
    step_from_tool_call,
    tool_result_event,
)
from app.modules.chat.application.turn_service import chat_turn_service
from app.modules.chat.generation.citations import cited_evidence_sources
from app.modules.chat.orchestration.direct import direct_orchestrator
from app.modules.chat.orchestration.react import react_orchestrator
from app.modules.chat.rag.generation import generate_answer_streaming, resolve_generation_target
from app.modules.chat.rag.graph.nodes import route_after_evidence_check
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.generator import generate_followup_suggestions

logger = logging.getLogger(__name__)


async def _finalize_as_error(assistant_message_id: str, full_tokens: list[str]) -> None:
    """Close a failed pending message while retaining already-streamed text."""

    await chat_turn_service.fail(assistant_message_id, "".join(full_tokens))


async def stream_suggestion_events(
    *,
    question: str,
    answer: str,
    context: str,
    identifiers: list[str],
    response_mode: str,
    history: list[dict],
    include_restricted: bool,
    model: str | None,
    user_id: str | None,
    evidence_sufficient: bool,
    assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """Generate, persist, and emit the shared follow-up-suggestion tail."""

    if not (evidence_sufficient and answer.strip()):
        yield encode_sse({"type": "answer_done", "suggestions_pending": False})
        yield encode_sse({"type": "done"})
        return

    sug_cfg = None
    suggestions_pending = False
    try:
        sug_cfg = await asyncio.to_thread(suggestions_service.active_config)
        suggestions_pending = bool(sug_cfg.enabled)
    except Exception:
        logger.exception("Suggestion settings unavailable; skipping follow-ups")

    yield encode_sse(
        {"type": "answer_done", "suggestions_pending": suggestions_pending}
    )

    if suggestions_pending and sug_cfg is not None:
        suggestions: list[str] = []
        try:
            suggestions = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_followup_suggestions,
                    question=question,
                    answer=answer,
                    context=context,
                    identifiers=identifiers,
                    response_mode=response_mode,
                    history=history,
                    include_restricted=include_restricted,
                    model=model,
                    user_id=user_id,
                    config=sug_cfg,
                ),
                timeout=45.0,
            )
        except Exception:
            logger.exception("Follow-up generation timed out or failed")

        try:
            await chat_turn_service.update_suggestions(assistant_message_id, suggestions)
        except Exception:
            logger.exception("Generated suggestions could not be persisted")
        yield encode_sse({"type": "suggestions", "items": suggestions})

    yield encode_sse({"type": "done"})


async def stream_agent_events(
    graph_input: dict | Command,
    *,
    config: dict,
    session_id: str,
    response_mode: str,
    answer_mode: str,
    assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """Drive the persisted ReAct graph and emit the frontend SSE protocol."""

    graph = react_orchestrator.graph()
    full_tokens: list[str] = []
    steps: list[dict] = await chat_turn_service.message_steps(assistant_message_id)
    interrupted = False

    try:
        async with aclosing(
            graph.astream(graph_input, config=config, stream_mode=["updates", "messages"])
        ) as stream:
            async for mode, chunk in stream:
                if mode == "messages":
                    message, meta = chunk
                    if meta.get("langgraph_node") == "final_generation" and getattr(
                        message, "content", None
                    ):
                        full_tokens.append(message.content)
                        yield encode_sse({"type": "token", "value": message.content})
                    continue

                if "__interrupt__" in chunk:
                    interrupts = chunk["__interrupt__"]
                    value: dict[str, Any] = dict(interrupts[0].value) if interrupts else {}
                    event_type = value.pop("type", "ask_user")
                    yield encode_sse({"type": event_type, "session_id": session_id, **value})
                    interrupted = True
                    break

                if "record_tool_call" in chunk:
                    call = chunk["record_tool_call"].get("last_tool_call")
                    if call:
                        reflection = call.get("reflection_on_previous_result")
                        if reflection and steps:
                            steps[-1]["reflection"] = reflection
                        steps.append(step_from_tool_call(call))
                        await chat_turn_service.update_steps(assistant_message_id, steps)
                        yield encode_sse({"type": "tool_call", **call})

                if "tools" in chunk:
                    for message in chunk["tools"].get("messages", []):
                        result_event = tool_result_event(message)
                        apply_tool_result(steps, result_event)
                        await chat_turn_service.update_steps(assistant_message_id, steps)
                        yield encode_sse(result_event)

                if "insufficient_evidence" in chunk:
                    for message in chunk["insufficient_evidence"].get("messages", []):
                        content = getattr(message, "content", "") or ""
                        full_tokens.append(content)
                        yield encode_sse({"type": "token", "value": content})

        if interrupted:
            return

        final_state = await graph.aget_state(config)
        values = final_state.values
        citations = values.get("citations", [])
        resolved_model = values.get("resolved_model")
        messages = values.get("messages", [])
        answer = "".join(full_tokens) or (
            messages[-1].content if messages and isinstance(messages[-1], AIMessage) else ""
        )

        evidence_sources = values.get("evidence_sources") or []
        evidence_sufficient = bool(evidence_sources)
        evidence_reason = None if evidence_sufficient else values.get("last_evidence_reason")
        reported_sources = cited_evidence_sources(evidence_sources, citations, answer)
        token_usage = aggregate_turn_token_usage(messages)

        await chat_turn_service.finalize_message(
            assistant_message_id,
            answer,
            citations,
            evidence_sufficient,
            response_mode,
            answer_mode,
            resolved_model,
            evidence_sources=reported_sources,
            token_usage=token_usage,
        )
        await chat_turn_service.touch(session_id)

        yield encode_sse(
            {
                "type": "citations",
                "data": citations,
                "evidence_sufficient": evidence_sufficient,
                "evidence_reason": evidence_reason,
                "evidence_sources": reported_sources,
                "token_usage": token_usage,
                "response_mode": response_mode,
                "answer_mode": answer_mode,
                "agent_mode": "react",
                "session_id": session_id,
                "model": resolved_model,
            }
        )

        context = "\n\n".join(c.get("quote", "") for c in citations if c.get("quote"))
        question = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        )
        suggestion_history = await chat_turn_service.history(session_id)
        async for event in stream_suggestion_events(
            question=question,
            answer=answer,
            context=context,
            identifiers=values.get("document_ids") or values.get("filenames") or [],
            response_mode=response_mode,
            history=suggestion_history,
            include_restricted=bool(values.get("include_restricted", False)),
            model=values.get("model"),
            user_id=values.get("user_id"),
            evidence_sufficient=evidence_sufficient,
            assistant_message_id=assistant_message_id,
        ):
            yield event

    except TimeoutError:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": "Request timed out."})
    except (FileNotFoundError, ValueError) as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": str(exc)})
    except Exception as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": f"Model request failed: {exc}"})


async def stream_direct_events(
    *,
    question: str,
    document_ids: list[str] | None,
    filenames: list[str] | None,
    model: str | None,
    response_mode: str,
    answer_mode: str,
    top_k: int,
    include_restricted: bool,
    history: list[dict],
    session_id: str,
    assistant_message_id: str,
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Drive the fixed one-retrieval Direct path and emit the same SSE protocol."""

    full_tokens: list[str] = []
    try:
        state = await asyncio.wait_for(
            asyncio.to_thread(
                direct_orchestrator.retrieve,
                question=question,
                document_ids=document_ids,
                filenames=filenames,
                model=model,
                response_mode=response_mode,
                answer_mode=answer_mode,
                top_k=top_k,
                include_restricted=include_restricted,
                history=history,
            ),
            timeout=120.0,
        )

        citations = state.get("citations", [])
        provider, selected_model, _config = resolve_generation_target(model)
        resolved_model = f"{provider}/{selected_model}"

        if route_after_evidence_check(state) == "insufficient_evidence":
            answer = get_insufficient_evidence_message(
                question=question,
                reason=state.get("evidence_reason") or "The retrieved excerpts are too weak.",
                mode=response_mode,
            )
            full_tokens.append(answer)
            yield encode_sse({"type": "token", "value": answer})
        else:
            async for chunk in generate_answer_streaming(
                question=question,
                context=state.get("context", ""),
                model=model,
                response_mode=response_mode,
                history=history,
                citations=citations,
                answer_mode=answer_mode,
            ):
                full_tokens.append(chunk)
                yield encode_sse({"type": "token", "value": chunk})

        answer = "".join(full_tokens)
        evidence_sufficient = state.get("evidence_sufficient", False)
        evidence_sources = ["internal"] if evidence_sufficient else []

        await chat_turn_service.finalize_message(
            assistant_message_id,
            answer,
            citations,
            evidence_sufficient,
            response_mode,
            answer_mode,
            resolved_model,
            evidence_sources=evidence_sources,
        )
        await chat_turn_service.touch(session_id)

        yield encode_sse(
            {
                "type": "citations",
                "data": citations,
                "evidence_sufficient": evidence_sufficient,
                "evidence_reason": state.get("evidence_reason"),
                "evidence_sources": evidence_sources,
                "response_mode": response_mode,
                "answer_mode": answer_mode,
                "agent_mode": "direct",
                "session_id": session_id,
                "model": resolved_model,
            }
        )

        async for event in stream_suggestion_events(
            question=question,
            answer=answer,
            context=state.get("context", ""),
            identifiers=document_ids or filenames or [],
            response_mode=response_mode,
            history=history,
            include_restricted=include_restricted,
            model=model,
            user_id=user_id,
            evidence_sufficient=evidence_sufficient,
            assistant_message_id=assistant_message_id,
        ):
            yield event

    except TimeoutError:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": "Request timed out."})
    except (FileNotFoundError, ValueError) as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": str(exc)})
    except Exception as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield encode_sse({"type": "error", "message": f"Model request failed: {exc}"})
