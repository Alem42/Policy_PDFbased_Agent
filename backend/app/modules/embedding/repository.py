"""Persistence for the embedding config (one JSON row in embedding_settings).

Uses the shared SingleRowSettings store — the same pattern every provider-backed
service (embedding, reranking, ...) follows. Falls back to defaults if the table
is empty/unavailable, so the app runs before migration 006 is applied.
"""

from __future__ import annotations

from app.core.settings_store import SingleRowSettings
from app.modules.embedding.settings import EmbeddingConfig


class EmbeddingSettingsRepository:
    def __init__(self) -> None:
        self._store = SingleRowSettings("embedding_settings")

    def load(self) -> EmbeddingConfig:
        return EmbeddingConfig(**self._store.load())

    def save(self, config: EmbeddingConfig) -> None:
        self._store.save(config.model_dump_json())


embedding_settings_repository = EmbeddingSettingsRepository()
