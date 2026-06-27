from collections.abc import AsyncIterator
from pathlib import Path

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
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
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
    if database.engine is None:
        return
    schema_path = BACKEND_ROOT / "supabase" / "local_schema.sql"
    sql = _read_sql(schema_path)
    async with database.engine.begin() as conn:
        await conn.execute(text(sql))


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")
