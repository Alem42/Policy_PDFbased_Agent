from app.core.config import get_settings
from app.core.llm_providers import DEFAULT_PROVIDER, PROVIDER_CONFIGS
from app.modules.settings.repository import settings_repository


def get_llm_api_key(provider: str | None = None) -> tuple[str | None, str]:
    """Resolve the API key for `provider` (defaults to the active default provider).

    Resolution order: per-provider runtime key -> legacy single runtime key
    (only for the default provider) -> per-provider env var -> legacy env var
    (only for the default provider).
    """
    runtime = settings_repository.load()
    provider = provider or get_llm_provider()
    default_provider = runtime.llm_provider or DEFAULT_PROVIDER

    runtime_key = runtime.provider_api_keys.get(provider)
    if not runtime_key and provider == default_provider:
        runtime_key = runtime.llm_api_key or runtime.deepseek_api_key
    if runtime_key:
        return runtime_key, "settings"

    settings = get_settings()
    environment_key = getattr(settings, f"{provider}_api_key", None)
    if not environment_key and provider == DEFAULT_PROVIDER:
        environment_key = settings.llm_api_key or settings.deepseek_api_key
    return (environment_key, "env") if environment_key else (None, "missing")


def get_llm_chat_model() -> tuple[str, str]:
    runtime = settings_repository.load()
    runtime_model = runtime.llm_chat_model or runtime.deepseek_chat_model
    if runtime_model:
        return runtime_model, "settings"

    settings = get_settings()
    environment_model = settings.llm_chat_model or settings.deepseek_chat_model
    if environment_model:
        return environment_model, "env"
    return settings.default_llm_chat_model, "default"


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_llm_provider() -> str:
    runtime = settings_repository.load()
    return runtime.llm_provider or DEFAULT_PROVIDER


def get_public_settings() -> dict:
    api_key, api_key_source = get_llm_api_key()
    model, model_source = get_llm_chat_model()
    masked_provider_keys = {
        provider: mask_api_key(get_llm_api_key(provider)[0]) for provider in PROVIDER_CONFIGS
    }
    return {
        "llm_configured": bool(api_key),
        "llm_api_key_source": api_key_source,
        "masked_llm_api_key": mask_api_key(api_key),
        "llm_chat_model": model,
        "llm_chat_model_source": model_source,
        "llm_base_url": get_settings().llm_base_url,
        "llm_provider": get_llm_provider(),
        "masked_provider_keys": masked_provider_keys,
    }


def update_public_settings(
    llm_api_key: str | None = None,
    llm_chat_model: str | None = None,
    llm_provider: str | None = None,
    provider_api_keys: dict[str, str] | None = None,
) -> dict:
    runtime = settings_repository.load()
    if llm_api_key is not None:
        runtime.llm_api_key = llm_api_key.strip() or None
        runtime.deepseek_api_key = None
    if llm_chat_model is not None:
        runtime.llm_chat_model = llm_chat_model.strip() or None
        runtime.deepseek_chat_model = None
    if llm_provider is not None:
        runtime.llm_provider = llm_provider.strip() or None
    if provider_api_keys is not None:
        updated_keys = dict(runtime.provider_api_keys)
        for provider, key in provider_api_keys.items():
            if provider not in PROVIDER_CONFIGS:
                continue
            key = (key or "").strip()
            if key:
                updated_keys[provider] = key
            else:
                updated_keys.pop(provider, None)
        runtime.provider_api_keys = updated_keys
    settings_repository.save(runtime)
    return get_public_settings()
