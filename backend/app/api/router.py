from fastapi import APIRouter

from app.modules.auth import router as auth
from app.modules.chat import router as chat
from app.modules.crawling.routers import documents as crawled_documents
from app.modules.crawling.routers import jobs as crawl_jobs
from app.modules.crawling.routers import sources as crawl_sources
from app.modules.documents import admin_router as admin
from app.modules.documents import router as documents
from app.modules.settings import router as settings
from app.modules.system import router as health

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
