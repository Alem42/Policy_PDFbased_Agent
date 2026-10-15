from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
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
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=5, ge=1)
    database_pool_timeout: float = Field(default=2.0, gt=0)
    database_pool_max_waiting: int = Field(default=20, ge=1)
    database_connect_timeout: int = Field(default=3, ge=1)
    database_pool_startup_timeout: float = Field(default=5.0, gt=0)
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    upload_chunk_bytes: int = Field(default=1024 * 1024, gt=0, le=8 * 1024 * 1024)
    upload_request_overhead_bytes: int = Field(default=256 * 1024, ge=0)
    runtime_settings_path: Path = Path("data/settings.json")
    document_task_workers: int = Field(default=3, ge=0, le=16)
    document_task_poll_seconds: float = Field(default=1, gt=0)
    document_task_lease_seconds: float = Field(default=30, ge=3)
    document_task_heartbeat_seconds: float = Field(default=5, gt=0)
    document_task_max_attempts: int = Field(default=3, ge=1, le=20)
    document_task_retry_seconds: float = Field(default=2, ge=0)
    document_task_execution_timeout_seconds: float = Field(default=300, ge=1)
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

    @model_validator(mode="after")
    def validate_pool_sizes(self) -> Self:
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE must not exceed DATABASE_POOL_MAX_SIZE")
        if self.document_task_heartbeat_seconds * 2 >= self.document_task_lease_seconds:
            raise ValueError("DOCUMENT_TASK_HEARTBEAT_SECONDS must be less than half the lease")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


DATA_DIR = BACKEND_ROOT / "data"
SETTINGS_PATH = BACKEND_ROOT / get_settings().runtime_settings_path
DATA_DIR.mkdir(parents=True, exist_ok=True)


def resolve_backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path
