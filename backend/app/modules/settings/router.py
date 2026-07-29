from typing import Annotated

from fastapi import APIRouter, Depends

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
    return update_public_settings(
        llm_api_key=payload.llm_api_key
        if payload.llm_api_key is not None
        else payload.deepseek_api_key,
        llm_chat_model=payload.llm_chat_model
        if payload.llm_chat_model is not None
        else payload.deepseek_chat_model,
        llm_provider=payload.llm_provider,
        provider_api_keys=payload.provider_api_keys,
    )
