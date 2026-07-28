"""Persistence for the embedding config (one JSON row in embedding_settings).

Kept deliberately tiny: the whole EmbeddingConfig is stored as a single jsonb
blob so adding a new tunable never needs a schema change. Falls back to defaults
if the table is empty or unavailable, so the app runs before migration 006.
"""

from __future__ import annotations

import json
import logging

from app.core.database import get_connection
from app.modules.embedding.settings import EmbeddingConfig

logger = logging.getLogger(__name__)

_ROW_ID = 1  # single-row table


class EmbeddingSettingsRepository:
    def load(self) -> EmbeddingConfig:
        try:
            with get_connection() as connection:
                row = connection.execute(
                    "SELECT config FROM embedding_settings WHERE id = %s", (_ROW_ID,)
                ).fetchone()
        except Exception as exc:
            logger.warning("embedding_settings unavailable, using defaults: %s", exc)
            return EmbeddingConfig()
        if not row or not row.get("config"):
            return EmbeddingConfig()
        data = row["config"]
        if isinstance(data, str):
            data = json.loads(data)
        return EmbeddingConfig(**data)

    def save(self, config: EmbeddingConfig) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO embedding_settings (id, config, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (id) DO UPDATE
                SET config = EXCLUDED.config, updated_at = now()
                """,
                (_ROW_ID, config.model_dump_json()),
            )
            connection.commit()


embedding_settings_repository = EmbeddingSettingsRepository()
