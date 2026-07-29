from __future__ import annotations

# Supported LLM provider identifiers (used in settings and frontend selector).
# Each entry maps a provider key to its default base URL, default model, any
# provider-specific extra_body fields required by that API, and the curated
# list of models selectable per-message from the chat UI.
#
# To add a new provider:
#   1. Add an entry here with its base_url, default_model, extra_body, and models.
#   2. Add the key to the frontend provider selector in SettingsPage.
#   3. If the provider needs a custom base URL (e.g. self-hosted), set
#      base_url to None and let the user configure llm_base_url in settings.
#   4. Add a `<provider>_api_key` field to Settings (config.py) and
#      RuntimeSettings (settings/schemas.py) so a key can be configured for it.

PROVIDER_CONFIGS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        # DeepSeek-specific: disable chain-of-thought "thinking" tokens so the
        # response returns the final answer only, without internal reasoning text.
        "extra_body": {"thinking": {"type": "disabled"}},
        "models": [
            {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash"},
            {"id": "deepseek-v4-pro", "label": "DeepSeek V4 Pro"},
        ],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "extra_body": {},
        "models": [
            {"id": "gpt-4o", "label": "GPT-4o"},
            {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
            {"id": "gpt-4.1", "label": "GPT-4.1"},
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        # Anthropic is accessed through its OpenAI-compatible endpoint.
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-5",
        "extra_body": {},
        "models": [
            {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"},
            {"id": "claude-sonnet-5", "label": "Claude Sonnet 5"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ],
    },
    "gemini": {
        "label": "Gemini",
        # Gemini is accessed through its OpenAI-compatible endpoint.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "extra_body": {},
        "models": [
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        ],
    },
    "custom": {
        "label": "Custom / self-hosted",
        # For self-hosted or OpenAI-compatible APIs (e.g. Ollama, vLLM).
        # base_url comes from the llm_base_url setting configured by the user.
        "base_url": None,
        "default_model": None,
        "extra_body": {},
        # No curated model list — the user types the model name directly.
        "models": [],
    },
}

DEFAULT_PROVIDER = "deepseek"


def get_provider_config(provider: str | None) -> dict:
    """Return the config dict for the given provider key.

    Falls back to DEFAULT_PROVIDER if the key is unknown or None.
    """
    provider = provider or DEFAULT_PROVIDER
    try:
        from app.modules.catalog.service import get_catalog

        catalog = get_catalog("chat")
        entries = [entry for entry in catalog["entries"] if entry["provider"] == provider]
        if entries:
            provider_row = next(
                (item for item in catalog.get("providers", []) if item["id"] == provider),
                None,
            )
            built_in = PROVIDER_CONFIGS.get(provider, {})
            return {
                "label": (provider_row or {}).get("label", entries[0]["provider_label"]),
                "base_url": (provider_row or {}).get("base_url") or entries[0]["base_url"],
                "default_model": entries[0]["model"],
                "extra_body": built_in.get("extra_body", {}),
                "models": [
                    {
                        "id": entry["model"],
                        "label": entry.get("model_display") or entry["model"],
                    }
                    for entry in entries
                ],
            }
    except Exception:
        pass
    return PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS[DEFAULT_PROVIDER])


def resolve_provider_and_model(model: str | None, default_provider: str) -> tuple[str, str | None]:
    """Split a `provider/model` identifier sent by the frontend.

    Per-message model selection encodes both provider and model id as
    "<provider>/<model-id>" (e.g. "openai/gpt-4o"). If `model` doesn't carry a
    known provider prefix, it's treated as a bare model name for the given
    default_provider (backward-compatible with older clients / global settings).
    """
    if model and "/" in model:
        provider, _, model_id = model.partition("/")
        try:
            from app.modules.catalog.service import get_catalog

            known_providers = {item["id"] for item in get_catalog().get("providers", [])}
        except Exception:
            known_providers = set(PROVIDER_CONFIGS)
        if provider in known_providers:
            return provider, model_id or None
    return default_provider, model
