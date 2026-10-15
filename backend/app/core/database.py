import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout, TooManyRequests
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


class DatabaseUnavailableError(RuntimeError):
    """A connection cannot be obtained within the configured resource budget."""


class Database:
    """Own the per-process Repository pool and the optional async session API."""

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.pool: ConnectionPool | None = None
        self._pool_lock = RLock()
        self.status = "disabled"

    def open_pool(self) -> ConnectionPool:
        """Also support CLI repositories, which do not run FastAPI lifespan."""
        with self._pool_lock:
            if self.pool is not None:
                return self.pool
            settings = get_settings()
            if not settings.database_enabled:
                raise DatabaseUnavailableError("Database access is disabled.")
            pool = ConnectionPool(
                conninfo=normalise_database_url(settings.database_url),
                kwargs={
                    "row_factory": dict_row,
                    "connect_timeout": settings.database_connect_timeout,
                },
                min_size=settings.database_pool_min_size,
                max_size=settings.database_pool_max_size,
                timeout=settings.database_pool_timeout,
                max_waiting=settings.database_pool_max_waiting,
                check=ConnectionPool.check_connection if settings.database_pool_pre_ping else None,
                open=False,
            )
            try:
                pool.open(wait=True, timeout=settings.database_pool_startup_timeout)
            except Exception:
                pool.close()
                raise
            self.pool = pool
            self.status = "configured"
            return pool

    def close_pool(self) -> None:
        with self._pool_lock:
            pool, self.pool = self.pool, None
            self.status = "disabled"
        if pool is not None:
            pool.close()

    def pool_stats(self) -> dict[str, int]:
        with self._pool_lock:
            return self.pool.get_stats() if self.pool is not None else {}

    async def connect(self) -> None:
        settings = get_settings()
        if not settings.database_enabled:
            self.status = "disabled"
            return
        await asyncio.to_thread(self.open_pool)
        try:
            self.engine = create_async_engine(
                settings.database_url,
                pool_pre_ping=settings.database_pool_pre_ping,
            )
            self.session_factory = async_sessionmaker(
                self.engine,
                expire_on_commit=False,
            )
        except Exception:
            await asyncio.to_thread(self.close_pool)
            raise

    async def disconnect(self) -> None:
        try:
            if self.engine is not None:
                await self.engine.dispose()
        finally:
            self.engine = None
            self.session_factory = None
            await asyncio.to_thread(self.close_pool)

    async def session(self) -> AsyncIterator[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("Database is not enabled or has not been connected")
        async with self.session_factory() as session:
            yield session


database = Database()


def normalise_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@contextmanager
def get_connection() -> Iterator[Any]:
    try:
        pool = database.open_pool()
        # Successful exit commits; exceptional exit rolls back; both return the
        # connection to the pool. Existing explicit Repository commits still work.
        with pool.connection() as connection:
            yield connection
    except (PoolTimeout, TooManyRequests, PoolClosed) as exc:
        raise DatabaseUnavailableError(
            "Database connection capacity is temporarily unavailable."
        ) from exc
