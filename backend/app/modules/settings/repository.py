import json

from app.core.config import SETTINGS_PATH
from app.modules.settings.schemas import RuntimeSettings


class SettingsRepository:
    """JSON-backed persistence for runtime configuration overrides."""

    def load(self) -> RuntimeSettings:
        if not SETTINGS_PATH.is_file():
            return RuntimeSettings()
        try:
            payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return RuntimeSettings()
        return RuntimeSettings.model_validate(payload)

    def save(self, settings: RuntimeSettings) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = SETTINGS_PATH.with_suffix(f"{SETTINGS_PATH.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(settings.model_dump(exclude_none=True), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(SETTINGS_PATH)


settings_repository = SettingsRepository()
