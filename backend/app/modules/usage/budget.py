"""Spending limit and prices for paid model APIs.

Version 1 enforces one limit for the whole deployment, per calendar month or in
total. Daily, per-user and per-conversation limits are stored but not enforced
yet, so the schema and the admin page do not change when they are added.
"""

import logging
from threading import Lock
from time import monotonic
from typing import Literal

from pydantic import BaseModel, Field

from app.core.database import get_connection
from app.core.settings_store import SingleRowSettings

logger = logging.getLogger(__name__)

# CNY per 1M tokens, or per request for web search. Defaults are estimates from
# public price lists; administrators should confirm them on each provider's page.
DEFAULT_PRICES = {
    "deepseek/*": {"input_per_million": 1.0, "output_per_million": 2.0},
    "deepseek/search": {"per_request": 0.0},
    "deepseek/fetch": {"per_request": 0.0},
    "zhipu/embedding-3": {"input_per_million": 0.5},
    "zhipu/embedding-2": {"input_per_million": 0.5},
    "zhipu/rerank": {"input_per_million": 0.0},
    "zhipu/*": {"input_per_million": 0.0, "output_per_million": 0.0},
}
SPEND_CACHE_SECONDS = 10.0


class Price(BaseModel):
    input_per_million: float = Field(default=0, ge=0)
    output_per_million: float = Field(default=0, ge=0)
    per_request: float = Field(default=0, ge=0)


class BudgetConfig(BaseModel):
    enabled: bool = False
    limit_cny: float | None = Field(default=None, ge=0)
    period: Literal["month", "total"] = "month"
    timezone: str = "Asia/Shanghai"
    prices: dict[str, Price] = Field(
        default_factory=lambda: {key: Price(**value) for key, value in DEFAULT_PRICES.items()}
    )
    # Reserved for later versions; stored and shown, not enforced yet.
    daily_limit_cny: float | None = Field(default=None, ge=0)
    per_user_monthly_limit_cny: float | None = Field(default=None, ge=0)
    per_conversation_limit_cny: float | None = Field(default=None, ge=0)

    def price_for(self, provider: str, model: str) -> Price:
        return (
            self.prices.get(f"{provider}/{model}")
            or self.prices.get(f"{provider}/*")
            or Price()
        )


class ApiBudgetExceeded(RuntimeError):
    """The deployment's API spending limit is reached; no request was sent."""


_store = SingleRowSettings("api_budget_settings")
_spend_lock = Lock()
_spend_cache: dict = {"value": None, "at": float("-inf"), "key": None}


def config() -> BudgetConfig:
    return BudgetConfig(**_store.load())


def save_config(payload: dict) -> BudgetConfig:
    merged = BudgetConfig(**{**config().model_dump(), **payload})
    _store.save(merged.model_dump_json())
    reset_spend_cache()
    return merged


def cost_of(provider: str, model: str, input_tokens: int, output_tokens: int, requests: int = 1):
    price = config().price_for(provider, model)
    return (
        input_tokens * price.input_per_million / 1_000_000
        + output_tokens * price.output_per_million / 1_000_000
        + requests * price.per_request
    )


def period_spend(cfg: BudgetConfig | None = None) -> float:
    """CNY spent in the current budget period, cached briefly per process."""
    cfg = cfg or config()
    key = (cfg.period, cfg.timezone)
    with _spend_lock:
        if _spend_cache["key"] == key and monotonic() - _spend_cache["at"] < SPEND_CACHE_SECONDS:
            return _spend_cache["value"]
    where = (
        "created_at >= date_trunc('month', now() AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s"
        if cfg.period == "month"
        else "TRUE"
    )
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(sum(cost_cny), 0) AS spent FROM api_usage_events WHERE {where}",
            {"tz": cfg.timezone},
        ).fetchone()
    value = float(row["spent"])
    with _spend_lock:
        _spend_cache.update(value=value, at=monotonic(), key=key)
    return value


def add_to_spend_cache(amount: float) -> None:
    with _spend_lock:
        if _spend_cache["value"] is not None:
            _spend_cache["value"] += amount


def reset_spend_cache() -> None:
    with _spend_lock:
        _spend_cache.update(value=None, at=float("-inf"), key=None)


def ensure_within_budget() -> None:
    """Raise before a paid request once the period's limit is used up."""
    try:
        cfg = config()
        if not cfg.enabled or cfg.limit_cny is None:
            return
        spent = period_spend(cfg)
    except Exception:  # noqa: BLE001 - a broken ledger must not stop the product
        logger.exception("API budget check failed; request allowed")
        return
    if spent >= cfg.limit_cny:
        raise ApiBudgetExceeded(
            f"The API budget of ¥{cfg.limit_cny:.2f} for this {cfg.period} is used up "
            f"(¥{spent:.2f} spent). An administrator can raise it under "
            "Manage → API usage & budget."
        )
