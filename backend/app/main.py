import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

if sys.platform == "win32":
    # psycopg's async mode (used by the LangGraph Postgres checkpointer) can't
    # run under ProactorEventLoop, which is asyncio's default on Windows.
    # Must be set before uvicorn creates its event loop, i.e. at import time.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import DatabaseUnavailableError, database
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.modules.chat.rag.checkpointer import close_checkpointer, init_checkpointer
from app.modules.documents.processing_queue import document_processing_queue


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    try:
        if get_settings().database_enabled:
            await init_checkpointer()
        await document_processing_queue.start()
        yield
    finally:
        await document_processing_queue.stop()
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
app.add_middleware(
    UploadBodyLimitMiddleware,
    upload_path=f"{settings.api_v1_prefix}/admin/documents",
    max_file_bytes=settings.upload_max_bytes,
    overhead_bytes=settings.upload_request_overhead_bytes,
)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable(_: Request, exc: DatabaseUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": "1"},
    )


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
