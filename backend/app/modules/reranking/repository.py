"""Persistence for the reranking config (one JSON row in reranking_settings)."""

from __future__ import annotations

from app.core.settings_store import SingleRowSettings
from app.modules.reranking.config import RerankingConfig


class RerankingSettingsRepository:
    def __init__(self) -> None:
        self._store = SingleRowSettings("reranking_settings")

    def load(self) -> RerankingConfig:
        return RerankingConfig(**self._store.load())

    def save(self, config: RerankingConfig) -> None:
        self._store.save(config.model_dump_json())


reranking_settings_repository = RerankingSettingsRepository()
