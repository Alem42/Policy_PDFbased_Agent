import json
from threading import RLock

from app.core.config import SETTINGS_PATH
from app.modules.settings.schemas import RuntimeSettings


class SettingsRepository:
    """JSON-backed runtime settings with a process-local read-through cache."""

    def __init__(self) -> None:
        self._cache: RuntimeSettings | None = None
        self._lock = RLock()

    def load(self) -> RuntimeSettings:
        with self._lock:
            if self._cache is None:
                if not SETTINGS_PATH.is_file():
                    self._cache = RuntimeSettings()
                else:
                    try:
                        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        payload = {}
                    self._cache = RuntimeSettings.model_validate(payload)
            return self._cache.model_copy(deep=True)

    def save(self, settings: RuntimeSettings) -> None:
        with self._lock:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = SETTINGS_PATH.with_suffix(f"{SETTINGS_PATH.suffix}.tmp")
            temporary_path.write_text(
                json.dumps(settings.model_dump(exclude_none=True), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(SETTINGS_PATH)
            self._cache = settings.model_copy(deep=True)

    def invalidate(self) -> None:
        """Force the next read to reload the settings file."""
        with self._lock:
            self._cache = None


settings_repository = SettingsRepository()
