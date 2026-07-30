import asyncio
import json as _json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.modules.auth.dependencies import get_current_user
from app.modules.catalog.service import get_catalog
from app.modules.chat.history_repository import chat_history_repository
from app.modules.chat.rag.agent.graph import get_agent_graph
from app.modules.chat.rag.generation import generate_answer_streaming, resolve_generation_target
from app.modules.chat.rag.graph.nodes import route_after_evidence_check
from app.modules.chat.rag.graph.state import normalize_answer_mode
from app.modules.chat.rag.graph.workflow import run_pdf_qa, run_retrieval
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.chat.schemas import (
    MAX_HISTORY_TURNS,
    ChatRequest,
    ChatResponse,
    Citation,
    ModelOption,
    ProviderModels,
    ResumeChatRequest,
)
from app.modules.settings.service import get_provider_api_key

router = APIRouter(tags=["rag"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/chat/models", response_model=list[ProviderModels])
async def list_models(_: CurrentUser) -> list[ProviderModels]:
    """List models selectable per-message, grouped by provider.

    Only providers with a configured API key are included so the chat UI
    never offers a model that would fail at request time.
    """
    available: list[ProviderModels] = []
    catalog = await asyncio.to_thread(get_catalog, "chat")
    providers = {item["id"]: item for item in catalog.get("providers", [])}
    provider_ids = list(dict.fromkeys(entry["provider"] for entry in catalog["entries"]))
    for provider in provider_ids:
        models = [
            entry for entry in catalog["entries"] if entry["provider"] == provider
        ]
        if not models:
            continue
        api_key = await asyncio.to_thread(get_provider_api_key, provider)
        if not api_key:
            continue
        available.append(
            ProviderModels(
                provider=provider,
                provider_label=providers.get(provider, {}).get("label", provider),
                models=[
                    ModelOption(
                        id=f"{provider}/{model['model']}",
                        label=model.get("model_display") or model["model"],
                    )
                    for model in models
                ],
            )
        )
    return available


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: CurrentUser,
) -> ChatResponse:
    doc_ids = [str(document_id) for document_id in payload.document_ids]
    filenames = list(payload.filenames or [])
    if not doc_ids and not filenames:
        raise HTTPException(status_code=400, detail="At least one document must be selected.")
    identifiers = doc_ids or filenames

    user_id = str(user["id"])
    effective_answer_mode = normalize_answer_mode(payload.response_mode, payload.answer_mode)

    # ── Session management ──────────────────────────────────────────────
    if payload.session_id is not None:
        session_id = str(payload.session_id)
        owns_session = await asyncio.to_thread(
            chat_history_repository.session_belongs_to_user,
            session_id,
            user_id,
        )
        if not owns_session:
            raise HTTPException(status_code=404, detail="Session not found.")

        # Read history from DB (more reliable than relying on the client to resend it).
        history = await asyncio.to_thread(
            chat_history_repository.get_history_for_llm,
            session_id,
            MAX_HISTORY_TURNS,
        )
    else:
        session_id = await asyncio.to_thread(
            chat_history_repository.create_session,
            user_id,
            payload.question[:80],
            identifiers,
            payload.response_mode,
        )
        # New session — no prior history.
        history = []

    try:
        # ── Save the user question immediately ─────────────────────────
        await asyncio.to_thread(
            chat_history_repository.add_message,
            session_id,
            "user",
            payload.question,
        )

        # run_pdf_qa is synchronous (LangGraph + CPU-bound embedding/reranking).
        # Running it in a thread pool prevents blocking the async event loop.
        result = await asyncio.wait_for(
            asyncio.to_thread(
                run_pdf_qa,
                question=payload.question,
                document_ids=doc_ids or None,
                filenames=filenames or None,
                model=payload.model,
                response_mode=payload.response_mode,
                answer_mode=effective_answer_mode,
                top_k=payload.top_k,
                include_restricted=user["role"] == "admin",
                history=history,
            ),
            timeout=120.0,
        )

        citations = [Citation(**c) for c in result.get("citations", [])]
        evidence_sufficient = result.get("evidence_sufficient", True)
        evidence_source = "internal" if evidence_sufficient else None

        resolved_model = result.get("resolved_model")

        # ── Save the assistant answer ───────────────────────────────────
        await asyncio.to_thread(
            chat_history_repository.add_message,
            session_id,
            "assistant",
            result["answer"],
            result.get("citations", []),
            evidence_sufficient,
            payload.response_mode,
            payload.answer_mode,
            resolved_model,
            "direct",
            evidence_source,
        )
        await asyncio.to_thread(chat_history_repository.touch_session, session_id)

        return ChatResponse(
            answer=result["answer"],
            citations=citations,
            truncated=result.get("truncated", False),
            evidence_sufficient=evidence_sufficient,
            evidence_reason=result.get("evidence_reason"),
            evidence_source=evidence_source,
            response_mode=payload.response_mode,
            answer_mode=effective_answer_mode,
            agent_mode="direct",
            session_id=UUID(session_id),
            model=resolved_model,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Request timed out after 120 s.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model request failed: {exc}") from exc


def _sse(obj: dict) -> str:
    return f"data: {_json.dumps(obj, default=str)}\n\n"


def _tool_result_event(message: Any) -> dict:
    """Return a compact, user-readable tool result summary for the trace UI."""
    result: dict = {}
    try:
        parsed = _json.loads(message.content)
        if isinstance(parsed, dict):
            result = parsed
    except (TypeError, ValueError):
        pass

    results = result.get("results")
    result_count = len(results) if isinstance(results, list) else None
    source_titles: list[str] = []
    if isinstance(results, list):
        for item in results:
            title = item.get("title") if isinstance(item, dict) else None
            if title and title not in source_titles:
                source_titles.append(str(title))
            if len(source_titles) == 5:
                break

    return {
        "type": "tool_result",
        "tool": getattr(message, "name", None),
        "evidence_sufficient": result.get("evidence_sufficient"),
        "evidence_reason": result.get("reason") or result.get("error"),
        "result_count": result_count,
        "source_titles": source_titles,
        "answer_plan": result.get("answer_plan"),
        "citation_numbers": result.get("citation_numbers"),
    }


def _step_from_tool_call(call: dict) -> dict:
    """Persisted-trace shape for a tool_call event — mirrors the step object
    ChatPage.jsx's consumeAgentStream builds client-side, minus `label`
    (recomputed on load from the tool name, same as the live view)."""
    return {
        "tool": call.get("tool"),
        "status": "running",
        "query": call.get("query"),
        "decisionReason": call.get("decision_reason"),
        "question": call.get("question"),
        "url": call.get("url"),
        "title": call.get("title"),
    }


def _apply_tool_result(steps: list[dict], result_event: dict) -> None:
    """Mutate the last matching "running" step in place to "done", mirroring
    the tool_result merge ChatPage.jsx does on its in-memory steps array."""
    for step in reversed(steps):
        if step.get("tool") == result_event.get("tool") and step.get("status") == "running":
            step["status"] = "done"
            step["evidenceSufficient"] = result_event.get("evidence_sufficient")
            step["evidenceReason"] = result_event.get("evidence_reason")
            step["resultCount"] = result_event.get("result_count")
            step["sourceTitles"] = result_event.get("source_titles") or []
            step["answerPlan"] = result_event.get("answer_plan")
            step["citationNumbers"] = result_event.get("citation_numbers") or []
            break


async def _stream_agent_events(
    graph_input: dict | Command,
    *,
    config: dict,
    session_id: str,
    response_mode: str,
    answer_mode: str,
    assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """Drive the agent graph (chat/rag/agent/graph.py) and translate its
    stream into the SSE event types the frontend understands.

    The assistant's chat_messages row (assistant_message_id) was already
    created by the caller before this generator starts — its reasoning_steps
    are updated once per tool call (not only once at the end), so a turn
    that's interrupted or crashes mid-stream still leaves a readable partial
    trace in history instead of losing it entirely.

    Event types:
      {"type": "tool_call", "tool": "..."}          — the agent is calling a tool
      {"type": "tool_result", "tool": "...", ...}    — that tool's result summary
      {"type": "token", "value": "..."}              — one text chunk of the final answer
      {"type": "ask_user", "mode": "confirm"|"choice"|"freeform", "question": ...,
       "options": [...] | null} — paused, call POST /chat/resume with
          {"session_id", "answer": "<one of options, or any free-typed text>"}
      {"type": "confirm_import", "url": ..., "title": ..., "question": ...} — paused,
          call POST /chat/resume with {"session_id", "answer": true|false}
      {"type": "citations", "data": [...], ...}      — final metadata (sent once)
      {"type": "done"}                                — stream complete
      {"type": "error", "message": "..."}             — terminal error
    """
    graph = get_agent_graph()
    full_tokens: list[str] = []
    # Seeded from the DB rather than starting empty: a resumed turn (after an
    # ask_user/confirm_import interrupt) is a fresh call to this generator,
    # so the steps recorded before the interrupt only live in the row.
    steps: list[dict] = await asyncio.to_thread(
        chat_history_repository.get_message_steps, assistant_message_id
    )

    interrupted = False
    try:
        # aclosing guarantees the inner astream generator's own cleanup runs
        # (flushing its last checkpoint write) even when we exit the loop
        # early on interrupt — a bare early `return` out of an `async for`
        # only abandons the generator, with no guaranteed timing on when (or
        # whether) it's finalized, which risks a client calling /chat/resume
        # before the paused checkpoint has actually been persisted.
        async with aclosing(
            graph.astream(graph_input, config=config, stream_mode=["updates", "messages"])
        ) as stream:
            async for mode, chunk in stream:
                if mode == "messages":
                    message, meta = chunk
                    if (
                        meta.get("langgraph_node") == "final_generation"
                        and getattr(message, "content", None)
                    ):
                        full_tokens.append(message.content)
                        yield _sse({"type": "token", "value": message.content})
                    continue

                # mode == "updates"
                if "__interrupt__" in chunk:
                    interrupts = chunk["__interrupt__"]
                    value: dict[str, Any] = dict(interrupts[0].value) if interrupts else {}
                    event_type = value.pop("type", "ask_user")
                    yield _sse({"type": event_type, "session_id": session_id, **value})
                    interrupted = True
                    break  # paused — client must call /chat/resume to continue

                if "record_tool_call" in chunk:
                    call = chunk["record_tool_call"].get("last_tool_call")
                    if call:
                        steps.append(_step_from_tool_call(call))
                        await asyncio.to_thread(
                            chat_history_repository.update_reasoning_steps,
                            assistant_message_id,
                            steps,
                        )
                        yield _sse({"type": "tool_call", **call})

                if "tools" in chunk:
                    for message in chunk["tools"].get("messages", []):
                        result_event = _tool_result_event(message)
                        _apply_tool_result(steps, result_event)
                        await asyncio.to_thread(
                            chat_history_repository.update_reasoning_steps,
                            assistant_message_id,
                            steps,
                        )
                        yield _sse(result_event)

                if "insufficient_evidence" in chunk:
                    # Document Analysis mode, no evidence tier ever became
                    # sufficient: this node's answer is a deterministic
                    # template (see graph.py::insufficient_evidence_node),
                    # not an LLM stream, so it never appears in "messages"
                    # mode — simulate one token event so the frontend renders
                    # it the same way as a normally-streamed answer.
                    for message in chunk["insufficient_evidence"].get("messages", []):
                        content = getattr(message, "content", "") or ""
                        full_tokens.append(content)
                        yield _sse({"type": "token", "value": content})

        if interrupted:
            return

        # Stream finished without interrupting: the graph reached END.
        final_state = await graph.aget_state(config)
        values = final_state.values
        citations = values.get("citations", [])
        resolved_model = values.get("resolved_model")
        messages = values.get("messages", [])
        answer = "".join(full_tokens) or (
            messages[-1].content if messages and isinstance(messages[-1], AIMessage) else ""
        )

        # "internal"/"full_corpus"/"web" — whichever retrieval tier last
        # returned evidence_sufficient=True this turn (see
        # agent/state.py::EvidenceSource); None covers both an Open
        # Discussion general-knowledge fallback and a Document Analysis
        # refusal (insufficient_evidence_node), which are told apart by
        # answer_mode on the frontend.
        evidence_source = values.get("evidence_source")
        evidence_sufficient = evidence_source is not None
        evidence_reason = None if evidence_sufficient else values.get("last_evidence_reason")

        await asyncio.to_thread(
            chat_history_repository.finalize_message,
            assistant_message_id,
            answer,
            citations,
            evidence_sufficient,
            response_mode,
            answer_mode,
            resolved_model,
            evidence_source=evidence_source,
        )
        await asyncio.to_thread(chat_history_repository.touch_session, session_id)

        yield _sse(
            {
                "type": "citations",
                "data": citations,
                "evidence_sufficient": evidence_sufficient,
                "evidence_reason": evidence_reason,
                "evidence_source": evidence_source,
                "response_mode": response_mode,
                "answer_mode": answer_mode,
                "agent_mode": "react",
                "session_id": session_id,
                "model": resolved_model,
            }
        )
        yield _sse({"type": "done"})

    except TimeoutError:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": "Request timed out."})
    except (FileNotFoundError, ValueError) as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": str(exc)})
    except Exception as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": f"Model request failed: {exc}"})


async def _finalize_as_error(assistant_message_id: str, full_tokens: list[str]) -> None:
    """Close out a pending message row that failed mid-stream, keeping
    whatever partial answer text had already streamed rather than losing it."""
    await asyncio.to_thread(
        chat_history_repository.finalize_message,
        assistant_message_id,
        "".join(full_tokens),
        status="error",
    )


async def _stream_direct_events(
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
) -> AsyncGenerator[str, None]:
    """Direct (non-ReAct) mode: one retrieval pass + a single streamed
    answer, with no tool-calling loop — so unlike _stream_agent_events, no
    tool_call/tool_result events are emitted and the message's
    reasoning_steps stays empty, correctly showing "no reasoning trace" for
    this mode. Reuses the same building blocks as the classic /chat endpoint
    (run_retrieval, generate_answer_streaming) and emits the same
    token/citations/done/error SSE shapes as _stream_agent_events so the
    frontend's stream consumer needs no branching by mode.
    """
    full_tokens: list[str] = []
    try:
        state = await asyncio.wait_for(
            asyncio.to_thread(
                run_retrieval,
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
            yield _sse({"type": "token", "value": answer})
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
                yield _sse({"type": "token", "value": chunk})

        answer = "".join(full_tokens)
        evidence_sufficient = state.get("evidence_sufficient", False)
        # Direct mode has only one evidence tier (the selected documents), so
        # this is trivially "internal" or nothing — see EvidenceSource in
        # agent/state.py for the richer ReAct-mode set.
        evidence_source = "internal" if evidence_sufficient else None

        await asyncio.to_thread(
            chat_history_repository.finalize_message,
            assistant_message_id,
            answer,
            citations,
            evidence_sufficient,
            response_mode,
            answer_mode,
            resolved_model,
            evidence_source=evidence_source,
        )
        await asyncio.to_thread(chat_history_repository.touch_session, session_id)

        yield _sse(
            {
                "type": "citations",
                "data": citations,
                "evidence_sufficient": evidence_sufficient,
                "evidence_reason": state.get("evidence_reason"),
                "evidence_source": evidence_source,
                "response_mode": response_mode,
                "answer_mode": answer_mode,
                "agent_mode": "direct",
                "session_id": session_id,
                "model": resolved_model,
            }
        )
        yield _sse({"type": "done"})

    except TimeoutError:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": "Request timed out."})
    except (FileNotFoundError, ValueError) as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": str(exc)})
    except Exception as exc:
        await _finalize_as_error(assistant_message_id, full_tokens)
        yield _sse({"type": "error", "message": f"Model request failed: {exc}"})


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: CurrentUser,
) -> StreamingResponse:
    """SSE streaming endpoint, driven by the tool-calling web-search agent
    (chat/rag/agent/graph.py). See _stream_agent_events for event types.
    """
    doc_ids = [str(d) for d in payload.document_ids]
    filenames = list(payload.filenames or [])
    if not doc_ids and not filenames:
        raise HTTPException(status_code=400, detail="At least one document must be selected.")

    user_id = str(user["id"])
    is_admin = user["role"] == "admin"
    effective_answer_mode = normalize_answer_mode(payload.response_mode, payload.answer_mode)

    if payload.session_id is not None:
        session_id = str(payload.session_id)
        owns = await asyncio.to_thread(
            chat_history_repository.session_belongs_to_user, session_id, user_id
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Session not found.")
    else:
        session_id = await asyncio.to_thread(
            chat_history_repository.create_session,
            user_id,
            payload.question[:80],
            doc_ids or filenames,
            payload.response_mode,
        )

    await asyncio.to_thread(
        chat_history_repository.add_message, session_id, "user", payload.question
    )
    # Created up front (not after the answer is ready) so tool-call trace
    # steps can be written to this row as they happen — see
    # _stream_agent_events and history_repository.create_pending_message.
    assistant_message_id = await asyncio.to_thread(
        chat_history_repository.create_pending_message,
        session_id,
        "assistant",
        payload.agent_mode,
    )

    if payload.agent_mode == "direct":
        # No LangGraph checkpointer involved in this mode — always read
        # conversation context straight from the DB, same as /chat.
        history = await asyncio.to_thread(
            chat_history_repository.get_history_for_llm, session_id, MAX_HISTORY_TURNS
        )
        return StreamingResponse(
            _stream_direct_events(
                question=payload.question,
                document_ids=doc_ids or None,
                filenames=filenames or None,
                model=payload.model,
                response_mode=payload.response_mode,
                answer_mode=effective_answer_mode,
                top_k=payload.top_k,
                include_restricted=is_admin,
                history=history,
                session_id=session_id,
                assistant_message_id=assistant_message_id,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = {"configurable": {"thread_id": session_id}}
    graph = get_agent_graph()
    # A brand-new thread has no prior checkpoint state — seed it with this
    # session's DB history so the agent has context. An existing thread
    # (continuing conversation, or a resumed interrupt) already carries its
    # own message history via the checkpointer, so only the new question is
    # appended — the DB history is not-reloaded there to avoid duplicating it.
    existing_state = await graph.aget_state(config)
    if existing_state.values.get("messages"):
        input_messages = [HumanMessage(content=payload.question)]
    else:
        history = await asyncio.to_thread(
            chat_history_repository.get_history_for_llm, session_id, MAX_HISTORY_TURNS
        )
        input_messages = [
            HumanMessage(content=h["content"])
            if h["role"] == "user"
            else AIMessage(content=h["content"])
            for h in history
        ]
        input_messages.append(HumanMessage(content=payload.question))

    graph_input = {
        "messages": input_messages,
        "document_ids": doc_ids,
        "filenames": filenames,
        "model": payload.model,
        "response_mode": payload.response_mode,
        "answer_mode": effective_answer_mode,
        "top_k": payload.top_k,
        "include_restricted": is_admin,
        "is_admin": is_admin,
        "user_id": user_id,
        # Non-empty reset marker guarantees the persisted LastValue channel is
        # overwritten for every new user question. Resume requests do not pass
        # graph_input, so the same question keeps its counts across interrupt().
        "tool_call_counts": {"__current_turn__": 1},
        # evidence_source/last_evidence_reason are also plain LastValue
        # channels (see agent/state.py) — explicitly reset them here for the
        # same reason as tool_call_counts above. Without this, a prior
        # question's successful search leaves evidence_source set in the
        # thread's persisted checkpoint, so a later question with genuinely
        # no evidence inherits the stale value: route_after_tools skips the
        # insufficient_evidence node and the SSE/DB metadata falsely reports
        # evidence_sufficient=true for an answer that was actually a refusal.
        "evidence_source": None,
        "last_evidence_reason": None,
        "assistant_message_id": assistant_message_id,
    }

    return StreamingResponse(
        _stream_agent_events(
            graph_input,
            config=config,
            session_id=session_id,
            response_mode=payload.response_mode,
            answer_mode=effective_answer_mode,
            assistant_message_id=assistant_message_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/resume")
async def chat_resume(
    payload: ResumeChatRequest,
    user: CurrentUser,
) -> StreamingResponse:
    """Resume a chat turn paused by interrupt() (an ask_user or
    confirm_import event from /chat/stream). Streams the same SSE event
    types as /chat/stream, continuing exactly where the agent left off.
    """
    session_id = str(payload.session_id)
    user_id = str(user["id"])
    owns = await asyncio.to_thread(
        chat_history_repository.session_belongs_to_user, session_id, user_id
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Session not found.")

    config = {"configurable": {"thread_id": session_id}}
    graph = get_agent_graph()
    state = await graph.aget_state(config)
    if not state.next:
        raise HTTPException(status_code=409, detail="This session has no paused turn to resume.")

    response_mode = state.values.get("response_mode", "researcher")
    answer_mode = state.values.get("answer_mode", "analysis")
    assistant_message_id = state.values.get("assistant_message_id")

    return StreamingResponse(
        _stream_agent_events(
            Command(resume=payload.answer),
            config=config,
            session_id=session_id,
            response_mode=response_mode,
            answer_mode=answer_mode,
            assistant_message_id=assistant_message_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
