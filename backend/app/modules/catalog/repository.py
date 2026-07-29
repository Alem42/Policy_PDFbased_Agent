"""Persistence for the model catalog (model_catalog table).

Seeded from data.DEFAULT_CATALOG on first read (like the taxonomy). Rows are
upserted on (provider, capability, model). Never stores API keys — only reusable
endpoint facts. Falls back to the in-code default if the table is unavailable.
"""

from __future__ import annotations

import logging
from threading import Lock
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import get_connection
from app.modules.catalog.data import (
    DEFAULT_CATALOG,
    DEFAULT_PROVIDERS,
    DEPRECATED_CATALOG_KEYS,
)

logger = logging.getLogger(__name__)

_COLUMNS = (
    "provider, provider_label, capability, model, base_url, endpoint, "
    "dimensions, openai_compatible, notes, sort_order"
)
_UPSERT_SQL = """
    INSERT INTO model_catalog
        (id, provider, provider_label, capability, model, base_url, endpoint,
         dimensions, openai_compatible, notes, sort_order)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (provider, capability, model) DO UPDATE
    SET provider_label = EXCLUDED.provider_label,
        base_url = EXCLUDED.base_url,
        endpoint = EXCLUDED.endpoint,
        dimensions = EXCLUDED.dimensions,
        openai_compatible = EXCLUDED.openai_compatible,
        notes = EXCLUDED.notes
"""


class ModelCatalogRepository:
    def is_empty(self) -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM model_catalog) e").fetchone()
        return not (row and row["e"])

    def seed(self, entries: list[dict]) -> None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    DELETE FROM model_catalog
                    WHERE provider = %s AND capability = %s AND model = %s
                    """,
                    DEPRECATED_CATALOG_KEYS,
                )
                cursor.executemany(
                    _UPSERT_SQL,
                    [self._values(entry, order) for order, entry in enumerate(entries)],
                )
            connection.commit()

    def add(self, entry: dict) -> None:
        with get_connection() as connection:
            self._upsert(connection, entry, entry.get("sort_order", 1000))
            connection.commit()

    def list(self, capability: str | None = None) -> list[dict]:
        clause = "WHERE capability = %s" if capability else ""
        values = (capability,) if capability else ()
        with get_connection() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM model_catalog {clause} "
                f"ORDER BY sort_order, provider, capability, model",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _upsert(connection, entry: dict, order: int) -> None:
        connection.execute(_UPSERT_SQL, ModelCatalogRepository._values(entry, order))

    @staticmethod
    def _values(entry: dict, order: int) -> tuple:
        return (
            str(uuid4()),
            entry["provider"],
            entry.get("provider_label", entry["provider"]),
            entry["capability"],
            entry["model"],
            entry.get("base_url", ""),
            entry.get("endpoint", ""),
            entry.get("dimensions"),
            entry.get("openai_compatible", True),
            entry.get("notes"),
            order,
        )


model_catalog_repository = ModelCatalogRepository()


class ModelProviderRepository:
    def seed(self, providers: list[dict]) -> None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO model_providers
                        (id, label, base_url, is_custom, sort_order, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (id) DO UPDATE
                    SET label = EXCLUDED.label,
                        base_url = EXCLUDED.base_url,
                        is_custom = EXCLUDED.is_custom,
                        updated_at = now()
                    """,
                    [
                        (
                            provider["id"],
                            provider["label"],
                            provider.get("base_url", ""),
                            bool(provider.get("is_custom", False)),
                            order,
                        )
                        for order, provider in enumerate(providers)
                    ],
                )
            connection.commit()

    def add(self, provider: dict) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO model_providers
                    (id, label, base_url, is_custom, sort_order, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE
                SET label = EXCLUDED.label,
                    base_url = EXCLUDED.base_url,
                    is_custom = EXCLUDED.is_custom,
                    updated_at = now()
                """,
                (
                    provider["id"],
                    provider["label"],
                    provider.get("base_url", ""),
                    bool(provider.get("is_custom", False)),
                    provider.get("sort_order", 1000),
                ),
            )
            connection.commit()

    def list(self) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, label, base_url, is_custom, sort_order
                FROM model_providers
                ORDER BY is_custom, sort_order, label
                """
            ).fetchall()
        return [dict(row) for row in rows]


model_provider_repository = ModelProviderRepository()
_defaults_synced = False
_provider_defaults_synced = False
_catalog_cache: tuple[dict, ...] | None = None
_provider_cache: tuple[dict, ...] | None = None
_catalog_cache_lock = Lock()


def invalidate_catalog_cache() -> None:
    """Clear cached catalog rows after an admin/crawler write."""
    global _catalog_cache
    with _catalog_cache_lock:
        _catalog_cache = None


def invalidate_provider_cache() -> None:
    global _provider_cache
    with _catalog_cache_lock:
        _provider_cache = None


def provider_entries() -> list[dict]:
    """Return active providers, cached after the first database read."""
    global _provider_cache, _provider_defaults_synced
    if not get_settings().database_enabled:
        return [dict(provider) for provider in DEFAULT_PROVIDERS]
    with _catalog_cache_lock:
        if _provider_cache is None:
            try:
                if not _provider_defaults_synced:
                    model_provider_repository.seed(DEFAULT_PROVIDERS)
                    _provider_defaults_synced = True
                rows = model_provider_repository.list()
                _provider_cache = tuple(dict(row) for row in (rows or DEFAULT_PROVIDERS))
            except Exception as exc:
                logger.warning("model_providers unavailable, using in-code defaults: %s", exc)
                _provider_cache = tuple(dict(provider) for provider in DEFAULT_PROVIDERS)
        rows = _provider_cache
    return [dict(provider) for provider in rows]


def catalog_entries(capability: str | None = None) -> list[dict]:
    """Live catalog rows, seeding the DB from DEFAULT_CATALOG on first use.

    Falls back to the in-code default if the DB is unavailable.
    """
    global _catalog_cache, _defaults_synced
    if not get_settings().database_enabled:
        return [
            dict(entry)
            for entry in DEFAULT_CATALOG
            if not capability or entry["capability"] == capability
        ]
    with _catalog_cache_lock:
        if _catalog_cache is None:
            try:
                # Upsert defaults once per process. The lock also prevents the
                # parallel catalog/settings requests on the admin page from
                # performing the same seed and SELECT twice.
                if not _defaults_synced:
                    model_catalog_repository.seed(DEFAULT_CATALOG)
                    _defaults_synced = True
                rows = model_catalog_repository.list()
                _catalog_cache = tuple(dict(row) for row in (rows or DEFAULT_CATALOG))
            except Exception as exc:
                logger.warning("model_catalog unavailable, using in-code default: %s", exc)
                _catalog_cache = tuple(dict(entry) for entry in DEFAULT_CATALOG)
        rows = _catalog_cache
    return [
        dict(entry)
        for entry in rows
        if not capability or entry["capability"] == capability
    ]
