import asyncio
import json as _json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import get_current_user
from app.modules.catalog.service import get_catalog
from app.modules.chat.history_repository import chat_history_repository
from app.modules.chat.rag.generation import generate_answer_streaming, resolve_generation_target
from app.modules.chat.rag.graph.state import normalize_answer_mode
from app.modules.chat.rag.graph.workflow import run_pdf_qa, run_retrieval
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.chat.suggestions import service as suggestions_service
from app.modules.chat.suggestions.generator import generate_followup_suggestions
from app.modules.chat.schemas import (
    MAX_HISTORY_TURNS,
    ChatRequest,
    ChatResponse,
    Citation,
    ModelOption,
    ProviderModels,
)
from app.modules.settings.service import get_provider_api_key

router = APIRouter(tags=["rag"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
logger = logging.getLogger(__name__)


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
                            include_restricted=user["role"] == "admin",
                            model=payload.model,
                            user_id=user_id,
                            config=sug_cfg,
                        ),
                        timeout=45.0,
                    )
                except Exception:
                    suggestions = []

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
            suggestions,
        )
        await asyncio.to_thread(chat_history_repository.touch_session, session_id)

        return ChatResponse(
            answer=result["answer"],
            citations=citations,
            truncated=result.get("truncated", False),
            evidence_sufficient=evidence_sufficient,
            evidence_reason=result.get("evidence_reason"),
            response_mode=payload.response_mode,
            answer_mode=effective_answer_mode,
            session_id=UUID(session_id),
            model=resolved_model,
            suggestions=suggestions,
        )
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
    """SSE streaming endpoint — yields tokens as they arrive from the LLM.

    Event types:
      {"type": "retrieving"}                    — retrieval phase started
      {"type": "thinking"}                      — LLM generation about to start
      {"type": "token", "value": "..."}         — one text chunk from the LLM
      {"type": "citations", "data": [...], ...} — final metadata (sent once)
      {"type": "answer_done", ...}              — answer is complete; suggestions may follow
      {"type": "suggestions", "items": [...]}   — validated follow-ups
      {"type": "done"}                          — stream connection complete
      {"type": "error", "message": "..."}       — terminal error
    """
    doc_ids = [str(d) for d in payload.document_ids]
    filenames = list(payload.filenames or [])
    if not doc_ids and not filenames:
        raise HTTPException(status_code=400, detail="At least one document must be selected.")

    user_id = str(user["id"])

    if payload.session_id is not None:
        session_id = str(payload.session_id)
        owns = await asyncio.to_thread(
            chat_history_repository.session_belongs_to_user, session_id, user_id
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Session not found.")
        history = await asyncio.to_thread(
            chat_history_repository.get_history_for_llm, session_id, MAX_HISTORY_TURNS
        )
    else:
        session_id = await asyncio.to_thread(
            chat_history_repository.create_session,
            user_id,
            payload.question[:80],
            doc_ids or filenames,
            payload.response_mode,
        )
        history = []

    async def event_generator() -> AsyncGenerator[str, None]:
        def _sse(obj: dict) -> str:
            return f"data: {_json.dumps(obj)}\n\n"

        full_tokens: list[str] = []
        citations: list[dict] = []
        evidence_sufficient = True
        evidence_reason: str | None = None
        resolved_model: str | None = None

        try:
            await asyncio.to_thread(
                chat_history_repository.add_message, session_id, "user", payload.question
            )

            yield _sse({"type": "retrieving"})

            state = await asyncio.wait_for(
                asyncio.to_thread(
                    run_retrieval,
                    question=payload.question,
                    document_ids=doc_ids or None,
                    filenames=filenames or None,
                    model=payload.model,
                    response_mode=payload.response_mode,
                    answer_mode=payload.answer_mode,
                    top_k=payload.top_k,
                    include_restricted=user["role"] == "admin",
                    history=history,
                ),
                timeout=60.0,
            )

            evidence_sufficient = bool(state.get("evidence_sufficient", False))
            evidence_reason = state.get("evidence_reason")
            citations = state.get("citations", [])
            effective_answer_mode = str(state.get("answer_mode", "analysis"))

            # Mirror route_after_evidence_check logic
            should_generate = evidence_sufficient or (
                effective_answer_mode == "chat" and payload.response_mode != "policymaker"
            )

            if should_generate:
                yield _sse({"type": "thinking"})
                # Resolved once up front (cheap, deterministic) so we know what
                # to persist/report even though generate_answer_streaming
                # resolves the same target again internally to build its client.
                provider, selected_model, _config = resolve_generation_target(payload.model)
                resolved_model = f"{provider}/{selected_model}"
                async for token in generate_answer_streaming(
                    question=payload.question,
                    context=state.get("context", ""),
                    model=payload.model,
                    response_mode=payload.response_mode,
                    answer_mode=effective_answer_mode,
                    history=history,
                    citations=citations,
                ):
                    full_tokens.append(token)
                    yield _sse({"type": "token", "value": token})
            else:
                refusal = get_insufficient_evidence_message(
                    question=payload.question,
                    reason=evidence_reason or "Too little relevant text was retrieved.",
                    mode=payload.response_mode,
                )
                full_tokens.append(refusal)
                citations = []
                yield _sse({"type": "token", "value": refusal})

            complete_answer = "".join(full_tokens)

            # Persist and publish the completed answer before starting the slower
            # suggestion pipeline. The frontend can stop rendering the answer as a
            # token stream and show a suggestion-specific progress indicator.
            sug_cfg = None
            suggestions_pending = False
            if evidence_sufficient and complete_answer.strip():
                try:
                    sug_cfg = await asyncio.to_thread(suggestions_service.active_config)
                    suggestions_pending = bool(sug_cfg.enabled)
                except Exception:
                    logger.exception("Suggestion settings unavailable; skipping follow-ups")

            assistant_message_id = await asyncio.to_thread(
                chat_history_repository.add_message,
                session_id,
                "assistant",
                complete_answer,
                citations,
                evidence_sufficient,
                payload.response_mode,
                payload.answer_mode,
                resolved_model,
                [],
            )
            await asyncio.to_thread(chat_history_repository.touch_session, session_id)

            yield _sse(
                {
                    "type": "citations",
                    "data": citations,
                    "evidence_sufficient": evidence_sufficient,
                    "evidence_reason": evidence_reason,
                    "response_mode": payload.response_mode,
                    "answer_mode": effective_answer_mode,
                    "session_id": session_id,
                    "model": resolved_model,
                }
            )
            yield _sse(
                {
                    "type": "answer_done",
                    "suggestions_pending": suggestions_pending,
                }
            )

            if suggestions_pending and sug_cfg is not None:
                suggestions: list[str] = []
                try:
                    suggestions = await asyncio.wait_for(
                        asyncio.to_thread(
                            generate_followup_suggestions,
                            question=payload.question,
                            answer=complete_answer,
                            context=state.get("context", ""),
                            identifiers=doc_ids or filenames,
                            response_mode=payload.response_mode,
                            history=history,
                            include_restricted=user["role"] == "admin",
                            model=payload.model,
                            user_id=user_id,
                            config=sug_cfg,
                        ),
                        timeout=45.0,
                    )
                except Exception:
                    logger.exception("Follow-up generation timed out or failed")

                try:
                    await asyncio.to_thread(
                        chat_history_repository.update_message_suggestions,
                        assistant_message_id,
                        suggestions,
                    )
                except Exception:
                    logger.exception("Generated suggestions could not be persisted")
                # Always emit the completion event, including an empty list, so
                # the frontend can clear its suggestion-specific loading state.
                yield _sse({"type": "suggestions", "items": suggestions})
            yield _sse({"type": "done"})

        except TimeoutError:
            yield _sse({"type": "error", "message": "Request timed out after 60 s."})
        except (FileNotFoundError, ValueError) as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse({"type": "error", "message": f"Model request failed: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
