from fastapi import APIRouter

from app.api.routes import crawl_jobs, crawled_documents, documents, health, sources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sources.router)
api_router.include_router(crawl_jobs.router)
api_router.include_router(documents.router)
api_router.include_router(crawled_documents.router)
