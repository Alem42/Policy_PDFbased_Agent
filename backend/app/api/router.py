from fastapi import APIRouter

from app.modules.auth.invite_router import router as admin_invites_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_admin_router
from app.modules.chat.agent_limits.router import router as agent_tool_limits_router
from app.modules.chat.history_router import router as chat_history_router
from app.modules.chat.router import router as chat_router
from app.modules.chat.suggestions.router import admin_router as suggestions_admin_router
from app.modules.chat.suggestions.router import user_router as suggestions_user_router
from app.modules.documents.admin_router import router as admin_documents_router
from app.modules.documents.router import router as documents_router
from app.modules.documents.taxonomy_router import router as taxonomy_router
from app.modules.embedding.router import router as embedding_admin_router
from app.modules.reranking.router import router as reranking_admin_router
from app.modules.settings.router import router as settings_router
from app.modules.system.router import router as system_router

api_router = APIRouter()

api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(admin_invites_router)
api_router.include_router(chat_router)
api_router.include_router(chat_history_router)
api_router.include_router(suggestions_admin_router)
api_router.include_router(suggestions_user_router)
api_router.include_router(documents_router)
api_router.include_router(admin_documents_router)
api_router.include_router(embedding_admin_router)
api_router.include_router(reranking_admin_router)
api_router.include_router(agent_tool_limits_router)
api_router.include_router(catalog_admin_router)
api_router.include_router(taxonomy_router)
api_router.include_router(settings_router)
