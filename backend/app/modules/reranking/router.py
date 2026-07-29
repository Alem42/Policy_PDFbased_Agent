"""Admin endpoints for reranking configuration (Manage > Reranker page).

    GET  /admin/reranking       -> current config (key masked) + status
    PUT  /admin/reranking       -> merge + persist config, return new status
    POST /admin/reranking/test  -> probe (local scores a pair; API hits /rerank)
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.reranking import service as reranking

router = APIRouter(prefix="/admin/reranking", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def get_reranking_settings(_: AdminUser) -> dict:
    return await asyncio.to_thread(reranking.status)


@router.put("")
async def update_reranking_settings(_: AdminUser, payload: dict = Body(...)) -> dict:
    try:
        await asyncio.to_thread(reranking.update_config, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(reranking.status)


@router.post("/test")
async def test_reranking_connection(_: AdminUser, payload: dict = Body(...)) -> dict:
    try:
        return await asyncio.to_thread(reranking.test_connection, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
