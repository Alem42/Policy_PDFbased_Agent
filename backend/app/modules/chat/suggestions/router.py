"""Suggestion endpoints.

Admin (Manage > Suggestions):
    GET /admin/suggestions   -> current config + status
    PUT /admin/suggestions   -> merge + persist config

User:
    POST /chat/suggestions/click  -> log that a suggested question was clicked
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID

from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.chat.suggestions import profile
from app.modules.chat.suggestions import service as suggestions

admin_router = APIRouter(prefix="/admin/suggestions", tags=["admin"])
user_router = APIRouter(prefix="/chat/suggestions", tags=["rag"])

AdminUser = Annotated[dict, Depends(require_admin)]
CurrentUser = Annotated[dict, Depends(get_current_user)]


@admin_router.get("")
async def get_suggestion_settings(_: AdminUser) -> dict:
    return await asyncio.to_thread(suggestions.status)


@admin_router.put("")
async def update_suggestion_settings(_: AdminUser, payload: dict = Body(...)) -> dict:
    try:
        await asyncio.to_thread(suggestions.update_config, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(suggestions.status)


class SuggestionClick(BaseModel):
    question: str
    session_id: UUID | None = None


@user_router.post("/click", status_code=204)
async def log_suggestion_click(payload: SuggestionClick, user: CurrentUser) -> None:
    # Best-effort logging for personalization; never fails the request.
    await asyncio.to_thread(
        profile.log_click,
        str(user["id"]),
        str(payload.session_id) if payload.session_id else None,
        payload.question,
    )
