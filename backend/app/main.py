import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

if sys.platform == "win32":
    # psycopg's async mode (used by the LangGraph Postgres checkpointer) can't
    # run under ProactorEventLoop, which is asyncio's default on Windows.
    # Must be set before uvicorn creates its event loop, i.e. at import time.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import database
from app.modules.chat.rag.checkpointer import close_checkpointer, init_checkpointer


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    await init_checkpointer()
    yield
    await close_checkpointer()
    await database.disconnect()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
