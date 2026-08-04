"""Admin endpoints for the model catalog.

    GET  /admin/catalog?capability=embedding  -> capabilities + entries
    POST /admin/catalog                        -> add/upsert one entry

New keys are entered on the LLM & API keys page (provider key store), not here.
Administrators can add or update individual endpoints through this API.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.catalog import service as catalog

router = APIRouter(prefix="/admin/catalog", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def list_catalog(_: AdminUser, capability: str | None = None) -> dict:
    return await asyncio.to_thread(catalog.get_catalog, capability)


@router.post("")
async def add_catalog_entry(payload: dict, _: AdminUser) -> dict:
    try:
        return await asyncio.to_thread(catalog.add_entry, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/providers")
async def add_catalog_provider(payload: dict, _: AdminUser) -> dict:
    try:
        return await asyncio.to_thread(catalog.add_provider, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
