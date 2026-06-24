from fastapi import APIRouter

from app.api.routes import admin, chat, crawlers, documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(admin.router)
api_router.include_router(chat.router)
api_router.include_router(crawlers.router)
