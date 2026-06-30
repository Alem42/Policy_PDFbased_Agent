from pydantic import BaseModel, ConfigDict


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm_api_key: str | None = None
    deepseek_api_key: str | None = None
    llm_chat_model: str | None = None
    deepseek_chat_model: str | None = None


class SettingsResponse(BaseModel):
    llm_configured: bool
    llm_api_key_source: str
    masked_llm_api_key: str | None
    llm_chat_model: str
    llm_chat_model_source: str
    llm_base_url: str


class SettingsUpdate(BaseModel):
    llm_api_key: str | None = None
    llm_chat_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_chat_model: str | None = None
