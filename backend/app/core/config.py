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

    app_name: str = "AI Policy Research Platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_enabled: bool = False
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_policy"
    database_pool_pre_ping: bool = False
    document_storage_dir: Path = Path("data/pdfs")
    legacy_document_storage_dir: Path = Path("data/pdf")
    vector_index_dir: Path = Path("data/vector_index")
    default_top_k: int = Field(default=6, ge=1, le=20)
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    model_cache_dir: Path = Path("data/model_cache")
    default_embedding_dimensions: int = 384
    max_context_characters: int = 200_000

    # Pages whose native (non-OCR) extracted text is shorter than this are
    # treated as scanned/image-only and re-read via OCR.
    ocr_min_text_chars: int = Field(default=20, ge=0)
    # Tesseract language pack(s), e.g. "eng", "chi_sim", or "eng+chi_sim".
    ocr_languages: str = "eng"
    # Explicit path to the tesseract binary. Leave unset to auto-detect via
    # PATH (Linux/Docker) or common Windows install locations.
    ocr_tesseract_cmd: str | None = None

    # Prefer APP_SECRET_FILE in containers so a unique key can be generated and
    # persisted without committing it or exposing it through container metadata.
    app_secret: str | None = None
    app_secret_file: Path = Path("data/app_secret")

    firecrawl_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


DATA_DIR = BACKEND_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def resolve_backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path
