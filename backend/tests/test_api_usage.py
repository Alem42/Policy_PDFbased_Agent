import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.core.database import get_connection
from app.modules.usage import budget, recorder
from app.modules.usage.context import bind, current, usage_scope
from app.modules.usage.middleware import UsageScopeMiddleware


def test_prices_use_exact_model_then_provider_wildcard(monkeypatch):
    cfg = budget.BudgetConfig(
        prices={
            "deepseek/*": budget.Price(input_per_million=2, output_per_million=8),
            "deepseek/deepseek-v4-pro": budget.Price(input_per_million=4),
            "deepseek/search": budget.Price(per_request=0.03),
        }
    )
    monkeypatch.setattr(budget, "config", lambda: cfg)
    assert budget.cost_of("deepseek", "deepseek-v4-flash", 1_000_000, 500_000) == pytest.approx(6)
    assert budget.cost_of("deepseek", "deepseek-v4-pro", 1_000_000, 0) == pytest.approx(4)
    assert budget.cost_of("deepseek", "search", 0, 0, requests=2) == pytest.approx(0.06)
    assert budget.cost_of("unknown", "model", 1_000_000, 1_000_000) == 0


def test_chat_callback_records_streamed_and_plain_usage(monkeypatch):
    rows = []
    monkeypatch.setattr(recorder, "record", lambda *args: rows.append(args))
    callback = recorder.UsageCallback("deepseek", "deepseek-v4-flash")
    message = AIMessage(
        content="ok", usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
    )
    callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
    callback.on_llm_end(
        LLMResult(
            generations=[[]],
            llm_output={"token_usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        )
    )
    assert rows == [
        ("deepseek", "deepseek-v4-flash", "chat", 120, 30),
        ("deepseek", "deepseek-v4-flash", "chat", 7, 3),
    ]


def test_budget_blocks_only_when_enabled_and_used_up(monkeypatch):
    cfg = budget.BudgetConfig(enabled=True, limit_cny=10)
    monkeypatch.setattr(budget, "config", lambda: cfg)
    monkeypatch.setattr(budget, "period_spend", lambda _cfg=None: 9.99)
    budget.ensure_within_budget()
    monkeypatch.setattr(budget, "period_spend", lambda _cfg=None: 10.0)
    with pytest.raises(budget.ApiBudgetExceeded):
        budget.ensure_within_budget()
    with pytest.raises(budget.ApiBudgetExceeded):
        recorder.UsageCallback("deepseek", "m").on_chat_model_start({}, [])
    cfg.enabled = False
    budget.ensure_within_budget()


def test_a_broken_ledger_never_blocks_requests(monkeypatch):
    def broken():
        raise RuntimeError("table missing")

    monkeypatch.setattr(budget, "config", broken)
    budget.ensure_within_budget()


def test_scope_crosses_thread_pools_only_when_bound():
    with usage_scope(area="documents", operation="metadata", document_id="d1"):
        bound = bind(current)
        plain = current
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(bound).result().operation == "metadata"
        assert pool.submit(plain).result().operation == "unknown"


def test_middleware_tags_area_and_token_user(monkeypatch):
    from app.modules.usage import middleware

    monkeypatch.setattr(middleware, "decode_access_token", lambda token: {"sub": "00042"})
    seen = {}

    async def app(scope, receive, send):
        seen["scope"] = current()

    wrapped = UsageScopeMiddleware(app, prefix="/api/v1")
    scope = {
        "type": "http",
        "path": "/api/v1/chat/stream",
        "headers": [(b"authorization", b"Bearer t")],
    }
    asyncio.run(wrapped(scope, None, None))
    assert (seen["scope"].area, seen["scope"].operation, seen["scope"].user_uid) == (
        "chat",
        "answer",
        "00042",
    )


def test_ledger_rows_and_admin_summary(postgres_repository):
    from app.modules.auth.repository import user_repository
    from app.modules.usage.router import _summary

    user = user_repository.create(f"usage-{uuid4().hex[:8]}", "u@example.test", "unused", "user")
    budget.save_config({"enabled": True, "limit_cny": 100})
    try:
        with usage_scope(area="chat", operation="answer", user_uid=user["uid"]):
            recorder.record("deepseek", "deepseek-v4-flash", "chat", 1_000_000, 0)
        with usage_scope(area="documents", operation="metadata"):
            recorder.record("zhipu", "embedding-3", "embedding", 2_000_000)
        budget.reset_spend_cache()
        assert budget.period_spend() == pytest.approx(1.0 + 1.0)

        summary = _summary("24h", "Asia/Shanghai")
        assert summary["totals"]["requests"] == 2
        assert {(r["provider"], r["model"]) for r in summary["by_model"]} == {
            ("deepseek", "deepseek-v4-flash"),
            ("zhipu", "embedding-3"),
        }
        users = {r["username"]: r["cost"] for r in summary["by_user"]}
        assert users[user["username"]] == pytest.approx(1.0)
        assert users["system / background"] == pytest.approx(1.0)
        assert {r["operation"] for r in summary["by_feature"]} == {"answer", "metadata"}
        assert summary["series"] and summary["bucket"] == "hour"
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM api_usage_events")
            conn.execute("DELETE FROM api_budget_settings")
            conn.execute("DELETE FROM app_users WHERE id = %s", (user["id"],))
        budget.reset_spend_cache()
