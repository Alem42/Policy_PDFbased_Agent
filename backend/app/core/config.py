from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Policy in Action Library Backend"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_enabled: bool = False
    database_url: str = "postgresql://postgres:postgres@localhost:5432/policy_library"

    crawling_enabled: bool = False
    document_storage_dir: Path = Path("data/pdfs")
    legacy_document_storage_dir: Path = Path("data/pdf")
    vector_index_dir: Path = Path("data/vector_index")
    default_top_k: int = Field(default=6, ge=1, le=20)
    default_embedding_dimensions: int = 384
    max_context_characters: int = 120_000

    llm_base_url: str = "https://api.deepseek.com"
    default_llm_chat_model: str = "deepseek-v4-flash"
    llm_api_key: str | None = None
    deepseek_api_key: str | None = None
    llm_chat_model: str | None = None
    deepseek_chat_model: str | None = None
    app_secret: str = "development-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()


DATA_DIR = BACKEND_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def resolve_backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path
