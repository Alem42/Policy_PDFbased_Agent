from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.settings.schemas import SettingsResponse, SettingsUpdate
from app.modules.settings.service import get_public_settings, update_public_settings

router = APIRouter(prefix="/settings", tags=["settings"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("", response_model=SettingsResponse)
async def get_settings(_: AdminUser) -> dict:
    return get_public_settings()


@router.put("", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    _: AdminUser,
) -> dict:
    try:
        return update_public_settings(
            llm_chat_model=payload.llm_chat_model,
            llm_provider=payload.llm_provider,
            provider_api_keys=payload.provider_api_keys,
            web_search_provider=payload.web_search_provider,
            web_search_provider_api_keys=payload.web_search_provider_api_keys,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
