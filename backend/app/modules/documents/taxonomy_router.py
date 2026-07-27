"""Policy taxonomy endpoints.

Public read (any authenticated user) powers the library filter bar and the edit
dialogs; admin write powers the global-management page. Both paths run the
blocking DB work in a thread pool to keep the event loop free.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.documents.taxonomy_schemas import TaxonomyResponse, TaxonomyUpdate
from app.modules.documents.taxonomy_service import get_taxonomy_tree, replace_taxonomy_tree

router = APIRouter(tags=["taxonomy"])


@router.get("/taxonomy", response_model=TaxonomyResponse)
async def read_taxonomy(_: Annotated[dict, Depends(get_current_user)]) -> dict:
    return {"groups": await asyncio.to_thread(get_taxonomy_tree)}


@router.put("/admin/taxonomy", response_model=TaxonomyResponse)
async def update_taxonomy(
    payload: TaxonomyUpdate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    groups = [group.model_dump() for group in payload.groups]
    return {"groups": await asyncio.to_thread(replace_taxonomy_tree, groups)}
