import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import BACKEND_ROOT, get_settings


class Database:
    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.status = "disabled"

    async def connect(self) -> None:
        settings = get_settings()
        if not settings.database_enabled:
            self.status = "disabled"
            return
        url = _to_asyncpg_url(settings.database_url)
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        self.status = "configured"

    async def disconnect(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
        self.status = "disabled"

    async def session(self) -> AsyncIterator[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("Database is not enabled or has not been connected")
        async with self.session_factory() as session:
            yield session


database = Database()


async def init_db() -> None:
    """Run the schema SQL once at startup using the sync psycopg connection.

    asyncpg (used by SQLAlchemy async engine) cannot execute multiple SQL
    statements in one call. psycopg3 has no such restriction, so we reuse
    get_connection() and offload the blocking I/O to a thread.
    """
    schema_path = BACKEND_ROOT / "supabase" / "local_schema.sql"
    if not schema_path.exists():
        return
    await asyncio.to_thread(_init_db_sync, schema_path)


def _init_db_sync(schema_path: Path) -> None:
    sql = _read_sql(schema_path)
    with get_connection() as conn:
        conn.execute(sql)
        conn.commit()


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _to_asyncpg_url(database_url: str) -> str:
    """Ensure the URL uses the asyncpg driver for SQLAlchemy async engine."""
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return database_url.replace("://", "+asyncpg://", 1)
    return database_url


def _normalise_database_url(database_url: str) -> str:
    """Convert asyncpg URL back to plain postgresql:// for sync psycopg."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(
        _normalise_database_url(settings.database_url),
        row_factory=dict_row,
    ) as connection:
        yield connection
