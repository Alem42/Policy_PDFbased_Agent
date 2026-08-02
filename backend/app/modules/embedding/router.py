"""Admin endpoints for embedding configuration (Manage > Embedding page).

    GET  /admin/embedding        -> current config (API key masked) + status
    PUT  /admin/embedding        -> merge + persist config, return new status
    POST /admin/embedding/test   -> probe connectivity, report real dimension

Sync service calls run in a worker thread so DB/network work never blocks the
event loop.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.embedding import service as embedding

router = APIRouter(prefix="/admin/embedding", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def get_embedding_settings(_: AdminUser) -> dict:
    return await asyncio.to_thread(embedding.status)


@router.put("")
async def update_embedding_settings(
    _: AdminUser, payload: Annotated[dict, Body()]
) -> dict:
    try:
        await asyncio.to_thread(embedding.update_config, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(embedding.status)


@router.post("/test")
async def test_embedding_connection(
    _: AdminUser, payload: Annotated[dict, Body()]
) -> dict:
    try:
        return await asyncio.to_thread(embedding.test_connection, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
