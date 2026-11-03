"""Persistence for the reranking config (one JSON row in reranking_settings)."""

from __future__ import annotations

import json

from app.core import secret_box
from app.core.settings_store import SingleRowSettings
from app.modules.reranking.config import RerankingConfig


class RerankingSettingsRepository:
    def __init__(self) -> None:
        self._store = SingleRowSettings("reranking_settings")

    def load(self) -> RerankingConfig:
        data = self._store.load()
        data["api_key"] = secret_box.decrypt(data.get("api_key")) or ""
        return RerankingConfig(**data)

    def version(self, max_age: float):
        return self._store.version(max_age)

    def loaded_version(self):
        return self._store.loaded_version()

    def save(self, config: RerankingConfig) -> None:
        data = config.model_dump(mode="json")
        data["api_key"] = secret_box.encrypt(data.get("api_key")) or ""
        self._store.save(json.dumps(data))


reranking_settings_repository = RerankingSettingsRepository()
