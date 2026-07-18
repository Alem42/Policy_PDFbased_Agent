from __future__ import annotations

# Supported LLM provider identifiers (used in settings and frontend selector).
# Each entry maps a provider key to its default base URL, default model, and
# any provider-specific extra_body fields required by that API.
#
# To add a new provider:
#   1. Add an entry here with its base_url, default_model, and extra_body.
#   2. Add the key to the frontend provider selector in SettingsPage.
#   3. If the provider needs a custom base URL (e.g. self-hosted), set
#      base_url to None and let the user configure llm_base_url in settings.

PROVIDER_CONFIGS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        # DeepSeek-specific: disable chain-of-thought "thinking" tokens so the
        # response returns the final answer only, without internal reasoning text.
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "extra_body": {},
    },
    "anthropic": {
        # Anthropic is accessed through its OpenAI-compatible endpoint.
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-5",
        "extra_body": {},
    },
    "custom": {
        # For self-hosted or OpenAI-compatible APIs (e.g. Ollama, vLLM).
        # base_url comes from the llm_base_url setting configured by the user.
        "base_url": None,
        "default_model": None,
        "extra_body": {},
    },
}

DEFAULT_PROVIDER = "deepseek"


def get_provider_config(provider: str | None) -> dict:
    """Return the config dict for the given provider key.

    Falls back to DEFAULT_PROVIDER if the key is unknown or None.
    """
    return PROVIDER_CONFIGS.get(provider or DEFAULT_PROVIDER, PROVIDER_CONFIGS[DEFAULT_PROVIDER])
