"""Admin views of paid API usage and the spending budget."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.core.database import get_connection
from app.modules.auth.dependencies import require_admin
from app.modules.usage import budget

router = APIRouter(prefix="/admin/usage", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]

RANGES = {"24h": (timedelta(hours=24), "hour"), "7d": (timedelta(days=7), "day"),
          "30d": (timedelta(days=30), "day"), "90d": (timedelta(days=90), "day"),
          "365d": (timedelta(days=365), "month")}


def _summary(range_key: str, tz: str) -> dict:
    span, bucket = RANGES[range_key]
    since = datetime.now(UTC) - span
    params = {"since": since, "tz": tz, "bucket": bucket}
    measures = (
        "COALESCE(sum(cost_cny), 0)::float AS cost, COALESCE(sum(input_tokens), 0)::bigint "
        "AS input_tokens, COALESCE(sum(output_tokens), 0)::bigint AS output_tokens, "
        "COALESCE(sum(requests), 0)::bigint AS requests"
    )
    where = "WHERE e.created_at >= %(since)s"
    with get_connection() as conn:
        def rows(sql):
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

        totals = rows(f"SELECT {measures} FROM api_usage_events e {where}")[0]
        series = rows(
            f"SELECT date_trunc(%(bucket)s, e.created_at AT TIME ZONE %(tz)s) AS bucket, "
            f"e.provider, {measures} FROM api_usage_events e {where} GROUP BY 1, 2 ORDER BY 1, 2"
        )
        by_model = rows(
            f"SELECT e.provider, e.model, e.kind, {measures} FROM api_usage_events e {where} "
            "GROUP BY 1, 2, 3 ORDER BY cost DESC, requests DESC"
        )
        by_feature = rows(
            f"SELECT e.area, e.operation, {measures} FROM api_usage_events e {where} "
            "GROUP BY 1, 2 ORDER BY cost DESC, requests DESC"
        )
        by_user = rows(
            f"SELECT COALESCE(u.username, 'system / background') AS username, {measures} "
            f"FROM api_usage_events e LEFT JOIN app_users u ON u.id = e.user_id {where} "
            "GROUP BY 1 ORDER BY cost DESC, requests DESC"
        )
        recent = rows(
            f"SELECT e.created_at, e.provider, e.model, e.kind, e.area, e.operation, "
            f"u.username, e.input_tokens, e.output_tokens, e.cost_cny::float AS cost "
            f"FROM api_usage_events e LEFT JOIN app_users u ON u.id = e.user_id {where} "
            "ORDER BY e.created_at DESC LIMIT 50"
        )
    for row in series:
        row["bucket"] = row["bucket"].isoformat()
    for row in recent:
        row["created_at"] = row["created_at"].isoformat()
    return {"range": range_key, "bucket": bucket, "timezone": tz, "since": since.isoformat(),
            "totals": totals, "series": series, "by_model": by_model,
            "by_feature": by_feature, "by_user": by_user, "recent": recent}


def _budget_view() -> dict:
    cfg = budget.config()
    budget.reset_spend_cache()
    spent = budget.period_spend(cfg)
    limit = cfg.limit_cny
    return {
        "settings": cfg.model_dump(),
        "spent_cny": spent,
        "remaining_cny": None if limit is None else max(limit - spent, 0),
        "used_ratio": None if not limit else min(spent / limit, 1),
        "blocking": bool(cfg.enabled and limit is not None and spent >= limit),
    }


@router.get("")
async def usage_summary(
    _: AdminUser,
    range: Literal["24h", "7d", "30d", "90d", "365d"] = "7d",  # noqa: A002 - API parameter
    tz: str = Query("UTC", max_length=64),
) -> dict:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Unknown time zone.") from exc
    return await asyncio.to_thread(_summary, range, tz)


@router.get("/budget")
async def get_budget(_: AdminUser) -> dict:
    return await asyncio.to_thread(_budget_view)


@router.put("/budget")
async def put_budget(payload: dict, _: AdminUser) -> dict:
    try:
        await asyncio.to_thread(budget.save_config, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc
    return await asyncio.to_thread(_budget_view)
