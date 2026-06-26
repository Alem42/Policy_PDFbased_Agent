from fastapi import APIRouter

from app.api.routes import crawled_documents, documents, health, jobs, sources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sources.router)
api_router.include_router(jobs.router)
api_router.include_router(documents.router)
api_router.include_router(crawled_documents.router)
