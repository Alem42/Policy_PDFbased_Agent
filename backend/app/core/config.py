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

    app_name: str = "Policy in Action Library Backend"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_enabled: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/policy_library"

    crawling_enabled: bool = False
    document_storage_dir: Path = Path("data/documents")
    vector_index_dir: Path = Path("data/vector_index")
    default_top_k: int = Field(default=6, ge=1, le=20)


@lru_cache
def get_settings() -> Settings:
    return Settings()
