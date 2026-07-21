from pydantic import BaseModel, ConfigDict, Field


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm_api_key: str | None = None  # legacy single-key fallback (pre-multi-provider)
    deepseek_api_key: str | None = None
    llm_chat_model: str | None = None
    deepseek_chat_model: str | None = None
    llm_provider: str | None = None  # default provider, e.g. "deepseek", "openai", "anthropic"
    # Per-provider API keys, keyed by provider id (see llm_providers.PROVIDER_CONFIGS).
    provider_api_keys: dict[str, str] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    llm_configured: bool
    llm_api_key_source: str
    masked_llm_api_key: str | None
    llm_chat_model: str
    llm_chat_model_source: str
    llm_base_url: str
    llm_provider: str  # default provider key
    # provider id -> masked key (or None if not configured for that provider)
    masked_provider_keys: dict[str, str | None]


class SettingsUpdate(BaseModel):
    llm_api_key: str | None = None
    llm_chat_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_chat_model: str | None = None
    llm_provider: str | None = None  # set to one of the keys in llm_providers.py
    # provider id -> new API key. Send "" to clear a provider's saved key.
    provider_api_keys: dict[str, str] | None = None
