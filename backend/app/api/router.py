from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    chat,
    crawl_jobs,
    crawl_sources,
    crawled_documents,
    documents,
    health,
    settings,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(settings.router)
api_router.include_router(crawl_sources.router)
api_router.include_router(crawl_jobs.router)
api_router.include_router(documents.router)
api_router.include_router(crawled_documents.router)
api_router.include_router(admin.router)
api_router.include_router(chat.router)
