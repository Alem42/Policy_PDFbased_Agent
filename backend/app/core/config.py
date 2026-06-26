from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Policy Research Platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    crawling_enabled: bool = False
    default_request_timeout_seconds: float = Field(default=30, gt=0, le=300)
    default_max_pages: int = Field(default=100, gt=0, le=10000)
    default_concurrency: int = Field(default=3, gt=0, le=20)
    user_agent: str = "AI-Policy-Research-Bot/0.1"

    database_enabled: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_policy"
    database_pool_pre_ping: bool = False
    persistence_backend: str = "database"
    crawled_document_store_path: Path = Path("data/state/crawled_documents.json")
    attachment_download_dir: Path = Path("data/attachments")

    firecrawl_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
