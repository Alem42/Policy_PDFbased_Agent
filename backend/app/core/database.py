from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.config import BACKEND_ROOT, get_settings


class DatabaseStatus:
    def __init__(self) -> None:
        self.status = "disabled"

    async def connect(self) -> None:
        self.status = "ready"

    async def disconnect(self) -> None:
        self.status = "disconnected"


database = DatabaseStatus()


def normalise_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(
        normalise_database_url(settings.database_url),
        row_factory=dict_row,
    ) as connection:
        yield connection


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def init_db() -> None:
    schema_path = BACKEND_ROOT / "supabase" / "local_schema.sql"
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(_read_sql(schema_path))
        connection.commit()
