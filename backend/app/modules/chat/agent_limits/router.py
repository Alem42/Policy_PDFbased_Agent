"""Admin endpoints for agent tool-call limits (Manage > Agent tool limits page).

    GET /admin/agent-tool-limits  -> current per-tool call budgets
    PUT /admin/agent-tool-limits  -> merge + persist budgets, return the new config
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.chat.agent_limits import service as agent_limits

router = APIRouter(prefix="/admin/agent-tool-limits", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def get_agent_tool_limits(_: AdminUser) -> dict:
    return await asyncio.to_thread(agent_limits.status)


@router.put("")
async def update_agent_tool_limits(_: AdminUser, payload: Annotated[dict, Body()]) -> dict:
    try:
        await asyncio.to_thread(agent_limits.update_config, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(agent_limits.status)
