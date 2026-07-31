"""Persistence for the suggestion config (one JSON row in suggestion_settings)."""

from __future__ import annotations

from app.core.settings_store import SingleRowSettings
from app.modules.chat.suggestions.config import SuggestionConfig


class SuggestionSettingsRepository:
    def __init__(self) -> None:
        self._store = SingleRowSettings("suggestion_settings")

    def load(self) -> SuggestionConfig:
        # SingleRowSettings falls back to {} if the table is missing, so defaults
        # apply cleanly before migration 006 is run.
        return SuggestionConfig(**self._store.load())

    def save(self, config: SuggestionConfig) -> None:
        self._store.save(config.model_dump_json())

    def invalidate(self) -> None:
        self._store.invalidate()


suggestion_settings_repository = SuggestionSettingsRepository()
