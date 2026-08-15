"""Minimal admin API for inspecting sanitized agent run traces."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.dependencies import require_admin
from app.modules.chat.runtime.repository import agent_run_repository

router = APIRouter(prefix="/admin/agent-runs", tags=["admin-agent-runs"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def list_agent_runs(
    _: AdminUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    return await asyncio.to_thread(agent_run_repository.list_runs, limit)


@router.get("/{run_id}")
async def get_agent_run(run_id: str, _: AdminUser) -> dict:
    result = await asyncio.to_thread(agent_run_repository.get_run, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent run not found.")
    return result
