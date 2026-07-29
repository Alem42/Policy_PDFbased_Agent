from pydantic import BaseModel, ConfigDict, Field


class RuntimeSettings(BaseModel):
    # Unknown fields from older settings.json versions are discarded the next
    # time the settings are saved.
    model_config = ConfigDict(extra="ignore")

    llm_provider: str | None = None
    llm_chat_model: str | None = None
    provider_api_keys: dict[str, str] = Field(default_factory=dict)
    web_search_provider: str | None = None
    web_search_provider_api_keys: dict[str, str] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    llm_configured: bool
    llm_provider: str
    llm_chat_model: str
    masked_provider_keys: dict[str, str | None]
    web_search_provider: str
    masked_web_search_provider_keys: dict[str, str | None]


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_chat_model: str | None = None
    # Provider id -> new API key. Send "" to clear a saved key.
    provider_api_keys: dict[str, str] | None = None
    web_search_provider: str | None = None
    # Provider id -> new API key. Send "" to clear a saved key.
    web_search_provider_api_keys: dict[str, str] | None = None
