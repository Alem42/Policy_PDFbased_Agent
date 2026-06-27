from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "crawling_enabled": settings.crawling_enabled,
        "database": database.status,
    }

