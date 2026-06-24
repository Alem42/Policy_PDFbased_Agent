from fastapi import APIRouter

from app.api.routes import documents, health, jobs, sources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sources.router)
api_router.include_router(jobs.router)
api_router.include_router(documents.router)
