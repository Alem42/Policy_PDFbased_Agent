from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.database import database
from app.core.redis_client import redis_runtime
from app.modules.auth.dependencies import require_admin

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "database": database.status,
        "redis": redis_runtime.status,
    }


@router.get("/admin/redis")
async def redis_status(_: Annotated[dict, Depends(require_admin)]) -> dict:
    await redis_runtime.probe()
    return redis_runtime.snapshot()


@router.get("/admin/database-pool")
def database_pool_status(_: Annotated[dict, Depends(require_admin)]) -> dict[str, object]:
    settings = get_settings()
    return {
        "scope": "per_process",
        "status": database.status,
        "limits": {
            "min_size": settings.database_pool_min_size,
            "max_size": settings.database_pool_max_size,
            "timeout_seconds": settings.database_pool_timeout,
            "max_waiting": settings.database_pool_max_waiting,
        },
        "stats": database.pool_stats(),
    }
