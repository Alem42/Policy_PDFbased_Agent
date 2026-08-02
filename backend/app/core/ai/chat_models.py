"""Application-wide construction of configured chat-model clients."""

from langchain_openai import ChatOpenAI

from app.core.llm_providers import get_provider_config, resolve_provider_and_model
from app.modules.settings.service import (
    get_llm_chat_model,
    get_llm_provider,
    get_provider_api_key,
)


def resolve_generation_target(model: str | None) -> tuple[str, str, dict]:
    """Resolve an optional ``provider/model`` selection to concrete settings."""

    default_provider = get_llm_provider()
    provider, requested_model = resolve_provider_and_model(model, default_provider)
    config = get_provider_config(provider)
    selected_model = (
        requested_model
        or (get_llm_chat_model() if provider == default_provider else None)
        or config["default_model"]
    )
    return provider, selected_model, config


def create_chat_client(
    provider: str,
    model: str,
    temperature: float = 0,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Build an OpenAI-compatible LangChain client for any catalog provider."""

    api_key = get_provider_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key is configured for provider '{provider}'.")
    config = get_provider_config(provider)
    options = {
        "api_key": api_key,
        "base_url": config["base_url"],
        "model": model,
        "temperature": temperature,
        "extra_body": config["extra_body"],
    }
    if max_tokens is not None:
        options["max_tokens"] = max_tokens
    return ChatOpenAI(**options)
