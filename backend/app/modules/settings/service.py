from app.core.llm_providers import DEFAULT_PROVIDER, get_provider_config
from app.modules.settings.repository import settings_repository


def _catalog() -> dict:
    from app.modules.catalog.service import get_catalog

    return get_catalog()


def _known_provider_ids() -> set[str]:
    return {provider["id"] for provider in _catalog().get("providers", [])}


def _chat_model_ids(provider: str) -> list[str]:
    return [
        entry["model"]
        for entry in _catalog()["entries"]
        if entry["provider"] == provider and entry["capability"] == "chat"
    ]


def get_llm_provider() -> str:
    return settings_repository.load().llm_provider or DEFAULT_PROVIDER


def get_llm_chat_model() -> str:
    provider = get_llm_provider()
    configured = settings_repository.load().llm_chat_model
    if configured and configured in _chat_model_ids(provider):
        return configured
    return get_provider_config(provider)["default_model"]


def get_provider_api_key(provider: str | None = None) -> str | None:
    provider_id = provider or get_llm_provider()
    return settings_repository.load().provider_api_keys.get(provider_id)


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_public_settings() -> dict:
    runtime = settings_repository.load()
    provider_ids = _known_provider_ids() | set(runtime.provider_api_keys)
    provider = get_llm_provider()
    model = get_llm_chat_model()
    key = get_provider_api_key(provider)
    return {
        "llm_configured": bool(key),
        "llm_provider": provider,
        "llm_chat_model": model,
        "masked_provider_keys": {
            provider_id: mask_api_key(get_provider_api_key(provider_id))
            for provider_id in sorted(provider_ids)
        },
    }


def update_public_settings(
    llm_chat_model: str | None = None,
    llm_provider: str | None = None,
    provider_api_keys: dict[str, str] | None = None,
) -> dict:
    runtime = settings_repository.load()
    provider_ids = _known_provider_ids()

    if llm_provider is not None:
        selected_provider = llm_provider.strip()
        if selected_provider not in provider_ids:
            raise ValueError(f"Unknown provider: {selected_provider!r}.")
        if not _chat_model_ids(selected_provider):
            raise ValueError(
                f"Provider '{selected_provider}' has no chat endpoint."
            )
        runtime.llm_provider = selected_provider

    effective_provider = runtime.llm_provider or DEFAULT_PROVIDER
    if llm_chat_model is not None:
        selected_model = llm_chat_model.strip()
        if selected_model not in _chat_model_ids(effective_provider):
            raise ValueError(
                f"Model '{selected_model}' is not a chat endpoint for "
                f"provider '{effective_provider}'."
            )
        runtime.llm_chat_model = selected_model
    elif runtime.llm_chat_model not in _chat_model_ids(effective_provider):
        runtime.llm_chat_model = None

    if provider_api_keys is not None:
        updated_keys = dict(runtime.provider_api_keys)
        allowed_providers = provider_ids | set(updated_keys)
        for provider, key in provider_api_keys.items():
            if provider not in allowed_providers:
                continue
            cleaned = (key or "").strip()
            if cleaned:
                updated_keys[provider] = cleaned
            else:
                updated_keys.pop(provider, None)
        runtime.provider_api_keys = updated_keys

    settings_repository.save(runtime)
    try:
        from app.modules.embedding import service as embedding

        embedding.invalidate_provider_cache()
    except Exception:
        pass
    return get_public_settings()
