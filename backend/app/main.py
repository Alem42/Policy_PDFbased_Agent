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
from app.core.concurrency_limit import ConcurrencyLimitMiddleware, chat_turn_limit
from app.core.config import get_settings
from app.core.database import DatabaseUnavailableError, database
from app.core.environment import require_project_interpreter
from app.core.redis_client import redis_runtime
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.modules.cache.taxonomy import taxonomy_cache
from app.modules.chat.rag.checkpointer import close_checkpointer, init_checkpointer
from app.modules.documents.processing_queue import document_processing_queue
from app.modules.documents.schema import validate_document_task_schema
from app.modules.evaluation.service import evaluation_worker
from app.modules.local_models.preload import preload_selected_models
from app.modules.usage.budget import ApiBudgetExceeded
from app.modules.usage.middleware import UsageScopeMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    require_project_interpreter()
    from app.modules.settings.repository import settings_repository

    # Reading once at startup encrypts any plaintext keys left by older versions.
    settings_repository.load()
    preload = None
    await database.connect()
    try:
        await redis_runtime.start()
        taxonomy_cache.reset()
        if get_settings().database_enabled:
            await asyncio.to_thread(validate_document_task_schema)
            await init_checkpointer()
        await document_processing_queue.start()
        await evaluation_worker.start()
        # Loading takes seconds; serve health checks meanwhile.
        preload = asyncio.create_task(asyncio.to_thread(preload_selected_models))
        yield
    finally:
        await evaluation_worker.stop()
        await document_processing_queue.stop()
        await close_checkpointer()
        await redis_runtime.close()
        await database.disconnect()
        from app.modules.local_models.runtime import local_model_runtime

        if preload is not None:
            await asyncio.gather(preload, return_exceptions=True)
        await asyncio.to_thread(local_model_runtime.unload)


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.add_middleware(UsageScopeMiddleware, prefix=settings.api_v1_prefix)
app.add_middleware(
    ConcurrencyLimitMiddleware,
    paths={
        f"{settings.api_v1_prefix}/chat",
        f"{settings.api_v1_prefix}/chat/stream",
        f"{settings.api_v1_prefix}/chat/resume",
    },
    limit=chat_turn_limit,
)
app.add_middleware(
    UploadBodyLimitMiddleware,
    upload_path=f"{settings.api_v1_prefix}/admin/documents",
    max_file_bytes=settings.upload_max_bytes,
    overhead_bytes=settings.upload_request_overhead_bytes,
)


@app.exception_handler(ApiBudgetExceeded)
async def api_budget_exceeded(_: Request, exc: ApiBudgetExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)})


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
