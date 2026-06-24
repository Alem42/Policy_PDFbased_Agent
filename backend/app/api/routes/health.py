from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "database_enabled": settings.database_enabled,
        "crawling_enabled": settings.crawling_enabled,
    }
