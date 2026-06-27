from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import database
from app.modules.crawling.repositories.job import crawl_job_repository


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    await crawl_job_repository.fail_interrupted_running_jobs()
    yield
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
