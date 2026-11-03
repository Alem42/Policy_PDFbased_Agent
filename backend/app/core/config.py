from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"
LEGACY_DATA_DIR = BACKEND_ROOT / "data"


def resolve_backend_path(path: Path) -> Path:
    return path if path.is_absolute() else BACKEND_ROOT / path


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
    redis_enabled: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = Field(default="policy:dev", pattern=r"^[A-Za-z0-9:_-]{1,100}$")
    redis_max_connections: int = Field(default=20, ge=1, le=500)
    redis_connect_timeout_seconds: float = Field(default=0.2, gt=0, le=5)
    redis_socket_timeout_seconds: float = Field(default=0.2, gt=0, le=5)
    redis_operation_budget_seconds: float = Field(default=0.3, gt=0, le=5)
    taxonomy_cache_enabled: bool = True
    taxonomy_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    taxonomy_cache_wait_seconds: float = Field(default=0.5, gt=0, le=5)
    taxonomy_cache_max_bytes: int = Field(default=256 * 1024, ge=1024, le=1024 * 1024)
    rate_limit_enabled: bool = False
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_chat_limit: int = Field(default=10, ge=1, le=10000)
    rate_limit_resume_limit: int = Field(default=20, ge=1, le=10000)
    rate_limit_upload_limit: int = Field(default=5, ge=1, le=10000)
    redis_demo_enabled: bool = False
    redis_demo_limit: int = Field(default=10, ge=1, le=10000)
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    upload_chunk_bytes: int = Field(default=1024 * 1024, gt=0, le=8 * 1024 * 1024)
    upload_request_overhead_bytes: int = Field(default=256 * 1024, ge=0)
    # Everything the backend writes lives under DATA_ROOT; keep it outside the code
    # checkout in deployments. The explicit paths below override single locations.
    data_root: Path = Path("data")
    runtime_settings_path: Path | None = None
    document_task_workers: int = Field(default=3, ge=0, le=16)
    # Chat turns (each one or more model calls) running at once per API process.
    chat_max_concurrent_turns: int = Field(default=8, ge=1, le=256)
    chat_queue_wait_seconds: float = Field(default=10, ge=0, le=120)
    # Refuse a different interpreter when this checkout has a project .venv.
    require_project_venv: bool = True
    # Load the selected local Qwen models at startup; free GPU memory after this many
    # seconds without a call. Each call restarts the countdown.
    local_models_preload: bool = True
    local_models_idle_seconds: int = Field(default=1800, ge=0, le=86400)
    document_task_poll_seconds: float = Field(default=1, gt=0)
    document_task_lease_seconds: float = Field(default=30, ge=3)
    document_task_heartbeat_seconds: float = Field(default=5, gt=0)
    document_task_max_attempts: int = Field(default=3, ge=1, le=20)
    document_task_retry_seconds: float = Field(default=2, ge=0)
    document_task_execution_timeout_seconds: float = Field(default=300, ge=1)
    document_storage_dir: Path | None = None
    legacy_document_storage_dir: Path = Path("data/pdf")
    vector_index_dir: Path = Path("data/vector_index")
    default_top_k: int = Field(default=6, ge=1, le=20)
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    model_cache_dir: Path | None = None
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
    app_secret_file: Path | None = None
    # Encrypts provider API keys at rest. Generated in secrets/ when unset.
    settings_encryption_key: str | None = None
    settings_key_file: Path | None = None

    firecrawl_api_key: str | None = None

    @model_validator(mode="after")
    def validate_pool_sizes(self) -> Self:
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE must not exceed DATABASE_POOL_MAX_SIZE")
        if self.rate_limit_enabled and not self.redis_enabled:
            raise ValueError("RATE_LIMIT_ENABLED requires REDIS_ENABLED")
        if self.document_task_heartbeat_seconds * 2 >= self.document_task_lease_seconds:
            raise ValueError("DOCUMENT_TASK_HEARTBEAT_SECONDS must be less than half the lease")
        return self

    def data_dir(self, *parts: str) -> Path:
        return resolve_backend_path(self.data_root).joinpath(*parts)

    def _located(self, explicit: Path | None, *parts: str, legacy: str) -> Path:
        if explicit is not None:
            return resolve_backend_path(explicit)
        current = self.data_dir(*parts)
        # Before `python -m app.modules.documents.migrate_storage`, keep using the
        # pre-DATA_ROOT location under backend/data.
        previous = LEGACY_DATA_DIR / legacy
        return previous if not current.exists() and previous.exists() else current

    @property
    def uploads_dir(self) -> Path:
        if self.document_storage_dir is not None:
            return resolve_backend_path(self.document_storage_dir)
        return self.data_dir("uploads")

    @property
    def model_cache_path(self) -> Path:
        return self._located(self.model_cache_dir, "model-cache", legacy="model_cache")

    @property
    def app_secret_path(self) -> Path:
        return self._located(self.app_secret_file, "secrets", "app_secret", legacy="app_secret")

    @property
    def settings_file_path(self) -> Path:
        return self._located(
            self.runtime_settings_path, "secrets", "settings.json", legacy="settings.json"
        )

    @property
    def settings_key_path(self) -> Path:
        return self._located(
            self.settings_key_file, "secrets", "settings.key", legacy="settings.key"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


SETTINGS_PATH = get_settings().settings_file_path
get_settings().data_dir().mkdir(parents=True, exist_ok=True)
