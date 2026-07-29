"""Persistence for the model catalog (model_catalog table).

Seeded from data.DEFAULT_CATALOG on first read (like the taxonomy). Rows are
upserted on (provider, capability, model). Never stores API keys — only reusable
endpoint facts. Falls back to the in-code default if the table is unavailable.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import get_connection
from app.modules.catalog.data import DEFAULT_CATALOG

logger = logging.getLogger(__name__)

_COLUMNS = (
    "provider, provider_label, capability, model, base_url, endpoint, "
    "dimensions, openai_compatible, notes, sort_order"
)


class ModelCatalogRepository:
    def is_empty(self) -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM model_catalog) e").fetchone()
        return not (row and row["e"])

    def seed(self, entries: list[dict]) -> None:
        with get_connection() as connection:
            for order, entry in enumerate(entries):
                self._upsert(connection, entry, order)
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
        connection.execute(
            """
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
            """,
            (
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
            ),
        )


model_catalog_repository = ModelCatalogRepository()
_defaults_synced = False


def catalog_entries(capability: str | None = None) -> list[dict]:
    """Live catalog rows, seeding the DB from DEFAULT_CATALOG on first use.

    Falls back to the in-code default if the DB is unavailable.
    """
    global _defaults_synced
    if not get_settings().database_enabled:
        return [
            entry
            for entry in DEFAULT_CATALOG
            if not capability or entry["capability"] == capability
        ]
    try:
        # Upsert defaults once per process. This keeps an existing deployment
        # in sync when the checked-in Zhipu reference expands, while preserving
        # all administrator-added rows.
        if not _defaults_synced:
            model_catalog_repository.seed(DEFAULT_CATALOG)
            _defaults_synced = True
        rows = model_catalog_repository.list(capability)
        return rows or [
            entry
            for entry in DEFAULT_CATALOG
            if not capability or entry["capability"] == capability
        ]
    except Exception as exc:
        logger.warning("model_catalog unavailable, using in-code default: %s", exc)
        return [e for e in DEFAULT_CATALOG if not capability or e["capability"] == capability]
