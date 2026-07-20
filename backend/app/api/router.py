from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.chat.history_router import router as chat_history_router
from app.modules.chat.router import router as chat_router
from app.modules.crawling.routers.documents import router as crawled_documents_router
from app.modules.crawling.routers.jobs import router as crawl_jobs_router
from app.modules.crawling.routers.sources import router as crawl_sources_router
from app.modules.documents.admin_router import router as admin_documents_router
from app.modules.documents.router import router as documents_router
from app.modules.settings.router import router as settings_router
from app.modules.system.router import router as system_router

api_router = APIRouter()

api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(chat_history_router)
api_router.include_router(documents_router)
api_router.include_router(admin_documents_router)
api_router.include_router(settings_router)
api_router.include_router(crawl_sources_router)
api_router.include_router(crawl_jobs_router)
api_router.include_router(crawled_documents_router)
