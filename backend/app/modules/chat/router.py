import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.modules.auth.dependencies import get_current_user
from app.modules.catalog.service import get_catalog
from app.modules.chat.application.models import StartTurnRequest
from app.modules.chat.application.streaming import (
    stream_agent_events,
    stream_direct_events,
)
from app.modules.chat.application.turn_service import (
    SessionNotFoundError,
    chat_turn_service,
)
from app.modules.chat.orchestration.direct import direct_orchestrator
from app.modules.chat.orchestration.react import react_orchestrator
from app.modules.chat.rag.graph.state import normalize_answer_mode
from app.modules.chat.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    ModelOption,
    ProviderModels,
    ResumeChatRequest,
)
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.generator import generate_followup_suggestions
from app.modules.retrieval.metadata_filters import metadata_filter_service
from app.modules.settings.service import get_provider_api_key

router = APIRouter(tags=["rag"])
CurrentUser = Annotated[dict, Depends(get_current_user)]

run_pdf_qa = direct_orchestrator.answer
get_agent_graph = react_orchestrator.graph


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
        models = [entry for entry in catalog["entries"] if entry["provider"] == provider]
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
    include_restricted = user["role"] == "admin"
    effective_answer_mode = normalize_answer_mode(payload.response_mode, payload.answer_mode)
    metadata_filters = await asyncio.to_thread(
        metadata_filter_service.infer,
        payload.question,
        payload.filters.model_dump(),
        include_restricted=include_restricted,
    )

    try:
        turn = await chat_turn_service.start(
            StartTurnRequest(
                user_id=user_id,
                question=payload.question,
                identifiers=tuple(identifiers),
                response_mode=payload.response_mode,
                agent_mode="direct",
                session_id=str(payload.session_id) if payload.session_id else None,
            )
        )
        session_id = turn.session_id
        history = turn.history

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
                include_restricted=include_restricted,
                history=history,
                metadata_filters=metadata_filters.as_dict(),
            ),
            timeout=120.0,
        )

        citations = [Citation(**c) for c in result.get("citations", [])]
        evidence_sufficient = result.get("evidence_sufficient", True)
        evidence_sources = ["internal"] if evidence_sufficient else []

        resolved_model = result.get("resolved_model")

        # Follow-up suggestions (Approach A + D), same guard as the streaming path.
        suggestions: list[str] = []
        if evidence_sufficient and str(result.get("answer", "")).strip():
            sug_cfg = await asyncio.to_thread(suggestions_service.active_config)
            if sug_cfg.enabled:
                try:
                    suggestions = await asyncio.wait_for(
                        asyncio.to_thread(
                            generate_followup_suggestions,
                            question=payload.question,
                            answer=result["answer"],
                            context=result.get("context", ""),
                            identifiers=doc_ids or filenames,
                            response_mode=payload.response_mode,
                            history=history,
                            include_restricted=include_restricted,
                            model=payload.model,
                            user_id=user_id,
                            config=sug_cfg,
                        ),
                        timeout=45.0,
                    )
                except Exception:
                    suggestions = []

        # ── Save the assistant answer ───────────────────────────────────
        await chat_turn_service.add_message(
            session_id,
            "assistant",
            result["answer"],
            result.get("citations", []),
            evidence_sufficient,
            payload.response_mode,
            payload.answer_mode,
            resolved_model,
            "direct",
            evidence_sources,
            suggestions,
        )
        await chat_turn_service.touch(session_id)

        return ChatResponse(
            answer=result["answer"],
            citations=citations,
            truncated=result.get("truncated", False),
            evidence_sufficient=evidence_sufficient,
            evidence_reason=result.get("evidence_reason"),
            evidence_sources=evidence_sources,
            response_mode=payload.response_mode,
            answer_mode=effective_answer_mode,
            agent_mode="direct",
            session_id=UUID(session_id),
            model=resolved_model,
            suggestions=suggestions,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Request timed out after 120 s.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model request failed: {exc}") from exc


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: CurrentUser,
) -> StreamingResponse:
    """Start a Direct or ReAct turn and return its stable SSE stream."""
    doc_ids = [str(d) for d in payload.document_ids]
    filenames = list(payload.filenames or [])
    if not doc_ids and not filenames:
        raise HTTPException(status_code=400, detail="At least one document must be selected.")

    user_id = str(user["id"])
    is_admin = user["role"] == "admin"
    effective_answer_mode = normalize_answer_mode(payload.response_mode, payload.answer_mode)
    metadata_filters = await asyncio.to_thread(
        metadata_filter_service.infer,
        payload.question,
        payload.filters.model_dump(),
        include_restricted=is_admin,
    )

    try:
        turn = await chat_turn_service.start(
            StartTurnRequest(
                user_id=user_id,
                question=payload.question,
                identifiers=tuple(doc_ids or filenames),
                response_mode=payload.response_mode,
                agent_mode=payload.agent_mode,
                session_id=str(payload.session_id) if payload.session_id else None,
                create_pending_assistant=True,
            )
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session_id = turn.session_id
    assistant_message_id = turn.assistant_message_id
    if assistant_message_id is None:  # defensive: requested above
        raise HTTPException(status_code=500, detail="Could not create assistant message.")

    if payload.agent_mode == "direct":
        return StreamingResponse(
            stream_direct_events(
                question=payload.question,
                document_ids=doc_ids or None,
                filenames=filenames or None,
                model=payload.model,
                response_mode=payload.response_mode,
                answer_mode=effective_answer_mode,
                top_k=payload.top_k,
                include_restricted=is_admin,
                history=turn.history,
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                user_id=user_id,
                metadata_filters=metadata_filters.as_dict(),
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
        input_messages = [
            HumanMessage(content=h["content"])
            if h["role"] == "user"
            else AIMessage(content=h["content"])
            for h in turn.history
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
        "metadata_filters": metadata_filters.as_dict(),
        "filter_fallback": False,
        "filter_notice": None,
        # Non-empty reset marker guarantees the persisted LastValue channel is
        # overwritten for every new user question. Resume requests do not pass
        # graph_input, so the same question keeps its counts across interrupt().
        "tool_call_counts": {"__current_turn__": 1},
        # evidence_sources/last_evidence_reason are also plain LastValue
        # fields (see agent/state.py) — explicitly reset them here for the
        # same reason as tool_call_counts above. Without this, a prior
        # question's successful search leaves evidence_sources set in the
        # thread's persisted checkpoint, so a later question with genuinely
        # no evidence inherits the stale value: route_after_tools skips the
        # insufficient_evidence node and the SSE/DB metadata falsely reports
        # evidence_sufficient=true for an answer that was actually a refusal.
        "evidence_sources": [],
        "last_evidence_reason": None,
        # Same reset reasoning as evidence_sources above — see
        # agent/state.py::AgentState.turn_citation_keys.
        "turn_citation_keys": [],
        "assistant_message_id": assistant_message_id,
    }

    return StreamingResponse(
        stream_agent_events(
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
    try:
        await chat_turn_service.require_session(session_id, user_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    config = {"configurable": {"thread_id": session_id}}
    graph = get_agent_graph()
    state = await graph.aget_state(config)
    if not state.next:
        raise HTTPException(status_code=409, detail="This session has no paused turn to resume.")

    response_mode = state.values.get("response_mode", "researcher")
    answer_mode = state.values.get("answer_mode", "analysis")
    assistant_message_id = state.values.get("assistant_message_id")

    return StreamingResponse(
        stream_agent_events(
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
