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

# Each API instance and worker process caches settings; this bounds how long a save
# made by another process can go unseen.
RECHECK_SECONDS = 2.0


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
            self.version()
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

    def loaded_version(self):
        """The updated_at of the row the cached config came from."""
        return self._version

    def version(self, max_age: float | None = None):
        """Latest saved updated_at, queried at most every max_age seconds.

        A newer row saved by another process drops the cache so the next load() rereads it.
        """
        max_age = RECHECK_SECONDS if max_age is None else max_age
        with self._lock:
            if self._cache is None or monotonic() - self._checked_at < max_age:
                return self._version
            self._checked_at = monotonic()
            try:
                with get_connection() as connection:
                    row = connection.execute(
                        f"SELECT updated_at FROM {self.table} WHERE id = 1"
                    ).fetchone()
            except Exception:
                return self._version
            version = row["updated_at"] if row else None
            if version != self._version:
                self._cache = None
            return version

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
