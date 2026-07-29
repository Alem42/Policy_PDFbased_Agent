"""Shared persistence for provider-backed service configs.

Every swappable "AI service" (embedding, reranking, and later web search) follows
the same shape:
  - a pydantic Config model (mirrors its admin page),
  - a single JSON row in a `<service>_settings` table,
  - a provider layer (local / API) hidden behind a service facade,
  - an admin router (GET/PUT/POST test).

This module supplies the common bit: a one-row JSON config store. It falls back
to an empty config if the table is missing, so the app still runs before the
service's migration is applied.
"""

from __future__ import annotations

import json
import logging

from app.core.database import get_connection

logger = logging.getLogger(__name__)


class SingleRowSettings:
    """Load/save one service's whole config as a single jsonb row (id = 1)."""

    def __init__(self, table: str) -> None:
        # `table` is a fixed internal constant per service, never user input.
        self.table = table

    def load(self) -> dict:
        try:
            with get_connection() as connection:
                row = connection.execute(
                    f"SELECT config FROM {self.table} WHERE id = 1"
                ).fetchone()
        except Exception as exc:
            logger.warning("%s unavailable, using defaults: %s", self.table, exc)
            return {}
        if not row or not row.get("config"):
            return {}
        data = row["config"]
        return json.loads(data) if isinstance(data, str) else data

    def save(self, config_json: str) -> None:
        with get_connection() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.table} (id, config, updated_at)
                VALUES (1, %s::jsonb, now())
                ON CONFLICT (id) DO UPDATE
                SET config = EXCLUDED.config, updated_at = now()
                """,
                (config_json,),
            )
            connection.commit()


def mask_secret(key: str | None) -> str | None:
    """Display-safe hint of a secret, never the raw value."""
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"
