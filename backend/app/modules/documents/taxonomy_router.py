"""Policy taxonomy endpoints.

Public read (any authenticated user) powers the library filter bar and the edit
dialogs; admin write powers the global-management page. Both paths run the
blocking DB work in a thread pool to keep the event loop free.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.cache.taxonomy import taxonomy_cache
from app.modules.documents.taxonomy_schemas import TaxonomyResponse, TaxonomyUpdate
from app.modules.documents.taxonomy_service import replace_taxonomy_tree

router = APIRouter(tags=["taxonomy"])


@router.get("/taxonomy", response_model=TaxonomyResponse)
async def read_taxonomy(response: Response, _: Annotated[dict, Depends(get_current_user)]) -> dict:
    payload, status = await taxonomy_cache.read()
    response.headers["X-Cache"] = status
    response.headers["Cache-Control"] = "no-store"
    return payload


@router.put("/admin/taxonomy", response_model=TaxonomyResponse)
async def update_taxonomy(
    payload: TaxonomyUpdate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    groups = [group.model_dump() for group in payload.groups]
    stored = await asyncio.to_thread(replace_taxonomy_tree, groups)
    await taxonomy_cache.invalidate()
    return {"groups": stored}
