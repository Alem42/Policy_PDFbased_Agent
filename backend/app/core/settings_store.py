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
from copy import deepcopy
from threading import RLock
from time import monotonic

from app.core.database import get_connection

logger = logging.getLogger(__name__)


class SingleRowSettings:
    """Load/save one service's whole config as a single jsonb row (id = 1)."""

    def __init__(self, table: str) -> None:
        # `table` is a fixed internal constant per service, never user input.
        self.table = table
        self._cache: dict | None = None
        self._version = None
        self._checked_at = float("-inf")
        self._lock = RLock()

    def load(self) -> dict:
        with self._lock:
            if self._cache is None:
                try:
                    with get_connection() as connection:
                        row = connection.execute(
                            f"SELECT config, updated_at FROM {self.table} WHERE id = 1"
                        ).fetchone()
                except Exception as exc:
                    logger.warning("%s unavailable, using defaults: %s", self.table, exc)
                    row = None
                self._version = row.get("updated_at") if row else None
                self._checked_at = monotonic()
                if not row or not row.get("config"):
                    self._cache = {}
                else:
                    data = row["config"]
                    self._cache = json.loads(data) if isinstance(data, str) else dict(data)
            return deepcopy(self._cache)

    def save(self, config_json: str) -> None:
        parsed = json.loads(config_json)
        with self._lock:
            with get_connection() as connection:
                row = connection.execute(
                    f"""
                    INSERT INTO {self.table} (id, config, updated_at)
                    VALUES (1, %s::jsonb, now())
                    ON CONFLICT (id) DO UPDATE
                    SET config = EXCLUDED.config, updated_at = now()
                    RETURNING updated_at
                    """,
                    (config_json,),
                ).fetchone()
                connection.commit()
            self._cache = parsed
            self._version = row["updated_at"] if row else None
            self._checked_at = monotonic()

    def changed(self, max_age: float) -> bool:
        """True once when another process saved a newer row; queries at most every max_age s.

        Each API instance and worker process caches the config, so without this an admin's
        model switch would only reach the process that handled the save.
        """
        with self._lock:
            if self._cache is None or monotonic() - self._checked_at < max_age:
                return False
            self._checked_at = monotonic()
            try:
                with get_connection() as connection:
                    row = connection.execute(
                        f"SELECT updated_at FROM {self.table} WHERE id = 1"
                    ).fetchone()
            except Exception:
                return False
            version = row["updated_at"] if row else None
            if version == self._version:
                return False
            self._cache = None
            return True

    def invalidate(self) -> None:
        """Force the next read to reload the database row."""
        with self._lock:
            self._cache = None


def mask_secret(key: str | None) -> str | None:
    """Display-safe hint of a secret, never the raw value."""
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"
