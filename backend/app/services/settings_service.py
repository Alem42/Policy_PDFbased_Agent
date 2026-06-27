from __future__ import annotations

import json

from app.core.config import SETTINGS_PATH, get_settings


def load_settings() -> dict:
    if not SETTINGS_PATH.is_file():
        return {}

    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _first_setting(settings: dict, *keys: str) -> tuple[str | None, str]:
    for key in keys:
        value = settings.get(key)
        if value:
            return value, "settings"
    return None, "missing"


def get_llm_api_key() -> tuple[str | None, str]:
    runtime_settings = load_settings()
    api_key, source = _first_setting(runtime_settings, "llm_api_key", "deepseek_api_key")
    if api_key:
        return api_key, source

    settings = get_settings()
    if settings.llm_api_key:
        return settings.llm_api_key, "env"
    if settings.deepseek_api_key:
        return settings.deepseek_api_key, "env"

    return None, "missing"


def get_llm_chat_model() -> tuple[str, str]:
    runtime_settings = load_settings()
    model, source = _first_setting(runtime_settings, "llm_chat_model", "deepseek_chat_model")
    if model:
        return model, source

    settings = get_settings()
    if settings.llm_chat_model:
        return settings.llm_chat_model, "env"
    if settings.deepseek_chat_model:
        return settings.deepseek_chat_model, "env"

    return settings.default_llm_chat_model, "default"


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_public_settings() -> dict:
    api_key, api_key_source = get_llm_api_key()
    model, model_source = get_llm_chat_model()
    return {
        "llm_configured": bool(api_key),
        "llm_api_key_source": api_key_source,
        "masked_llm_api_key": mask_api_key(api_key),
        "llm_chat_model": model,
        "llm_chat_model_source": model_source,
        "llm_base_url": get_settings().llm_base_url,
    }


def update_public_settings(
    llm_api_key: str | None = None,
    llm_chat_model: str | None = None,
) -> dict:
    runtime_settings = load_settings()

    if llm_api_key is not None:
        clean_api_key = llm_api_key.strip()
        if clean_api_key:
            runtime_settings["llm_api_key"] = clean_api_key
        else:
            runtime_settings.pop("llm_api_key", None)
            runtime_settings.pop("deepseek_api_key", None)

    if llm_chat_model is not None:
        clean_model = llm_chat_model.strip()
        if clean_model:
            runtime_settings["llm_chat_model"] = clean_model
        else:
            runtime_settings.pop("llm_chat_model", None)
            runtime_settings.pop("deepseek_chat_model", None)

    save_settings(runtime_settings)
    return get_public_settings()
