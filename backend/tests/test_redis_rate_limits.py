import asyncio
import os
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.redis_client import RedisRuntime
from app.main import app
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.chat import router as chat_router
from app.modules.documents import admin_router
from app.modules.rate_limits.service import RateLimiter, rate_limiter
from app.modules.system import router as system_router


def limiter_with_result(result=None, error=None):
    runtime = RedisRuntime()
    runtime.settings = Settings(_env_file=None, redis_enabled=True, rate_limit_enabled=True)
    runtime.client = Mock()
    runtime.client.eval = AsyncMock(return_value=result, side_effect=error)
    return RateLimiter(runtime), runtime


def test_invalid_rate_configuration_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_enabled=True, redis_enabled=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_chat_limit=0)


async def test_disabled_gate_never_calls_redis():
    runtime = RedisRuntime()
    runtime.settings = Settings(_env_file=None)
    assert await RateLimiter(runtime).enforce(str(uuid4()), "chat") is None
    assert runtime.snapshot()["counters"].get("redis_operations", 0) == 0


async def test_allowed_and_denied_have_bounded_retry_and_metrics():
    limiter, runtime = limiter_with_result([1, 9, 59999])
    user = str(uuid4())
    result = await limiter.enforce(user, "chat")
    assert result.remaining == 9
    assert result.retry_after_seconds == 60
    assert runtime.client.eval.call_args.args[2].endswith(f":chat:user:{user}")
    runtime.client.eval.return_value = [0, 0, 1001]
    with pytest.raises(HTTPException) as caught:
        await limiter.enforce(user, "chat")
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "2"
    counts = runtime.snapshot()["counters"]
    assert counts["rate_chat_allowed"] == counts["rate_chat_denied"] == 1


@pytest.mark.parametrize("result", [None, [1, 0], [True, 2, 1000], [1, 10, 5], [0, 0, -1]])
async def test_invalid_script_result_fails_closed(result):
    limiter, runtime = limiter_with_result(result)
    with pytest.raises(HTTPException) as caught:
        await limiter.enforce(str(uuid4()), "upload")
    assert caught.value.status_code == 503
    assert runtime.client.eval.await_count == 1


async def test_network_error_does_not_retry_debit():
    limiter, runtime = limiter_with_result(error=RedisConnectionError("offline"))
    with pytest.raises(HTTPException) as caught:
        await limiter.enforce(str(uuid4()), "chat")
    assert caught.value.status_code == 503
    assert runtime.client.eval.await_count == 1
    assert runtime.status == "degraded"


@pytest.mark.parametrize("code", [429, 503])
def test_chat_stream_upload_and_resume_gate_before_side_effects(monkeypatch, code):
    user = {"id": str(uuid4()), "role": "admin"}
    gate = AsyncMock(side_effect=HTTPException(code, "limited", headers={"Retry-After": "1"}))
    infer, save, graph = Mock(), AsyncMock(), Mock()
    start, ownership = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rate_limiter, "enforce", gate)
    monkeypatch.setattr(chat_router.metadata_filter_service, "infer", infer)
    monkeypatch.setattr(chat_router.chat_turn_service, "start", start)
    monkeypatch.setattr(chat_router.chat_turn_service, "require_session", ownership)
    monkeypatch.setattr(chat_router, "get_agent_graph", graph)
    monkeypatch.setattr(admin_router, "save_upload", save)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    try:
        with TestClient(app) as client:
            for path in ("/chat", "/chat/stream"):
                response = client.post(
                    "/api/v1" + path,
                    json={"question": "What is the budget?", "document_ids": [str(uuid4())]},
                )
                assert response.status_code == code
                assert "text/event-stream" not in response.headers.get("content-type", "")
            response = client.post(
                "/api/v1/admin/documents", files={"file": ("test.pdf", b"%PDF-test")}
            )
            assert response.status_code == code
            response = client.post(
                "/api/v1/chat/resume", json={"session_id": str(uuid4()), "answer": "Yes"}
            )
            assert response.status_code == code
        assert [call.args[1] for call in gate.await_args_list] == [
            "chat",
            "chat",
            "upload",
            "resume",
        ]
        ownership.assert_awaited_once()
        infer.assert_not_called()
        start.assert_not_awaited()
        save.assert_not_awaited()
        graph.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("environment", "enabled", "expected"),
    [("production", True, 404), ("development", False, 404), ("development", True, 200)],
)
def test_demo_requires_development_and_explicit_switch(monkeypatch, environment, enabled, expected):
    settings = Settings(_env_file=None, app_env=environment, redis_demo_enabled=enabled)
    monkeypatch.setattr(system_router, "get_settings", lambda: settings)
    gate = AsyncMock(return_value=None)
    monkeypatch.setattr(rate_limiter, "enforce", gate)
    app.dependency_overrides[require_admin] = lambda: {"id": str(uuid4()), "role": "admin"}
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/admin/redis/limited-ping").status_code == expected
        assert gate.await_count == (1 if expected == 200 else 0)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_real_redis_two_clients_isolation_expiry_and_corruption():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to a disposable Redis instance.")
    prefix = "policy:test:" + uuid4().hex
    settings = Settings(
        _env_file=None,
        redis_enabled=True,
        redis_url=url,
        redis_key_prefix=prefix,
        rate_limit_enabled=True,
        rate_limit_window_seconds=1,
    )
    a, b = RedisRuntime(), RedisRuntime()
    await a.start(settings)
    await b.start(settings)
    one, two = RateLimiter(a), RateLimiter(b)
    user, other = str(uuid4()), str(uuid4())
    key = f"{prefix}:rl:v1:chat:user:{user}"

    async def admit(limiter, user_id=user, rule="chat"):
        try:
            await limiter.enforce(user_id, rule)
            return 200
        except HTTPException as exc:
            return exc.status_code

    try:
        statuses = await asyncio.gather(*(admit(one if i % 2 else two) for i in range(40)))
        assert statuses.count(200) == 10
        assert statuses.count(429) == 30
        assert await a.client.get(key) == "10"
        ttl = await a.client.pttl(key)
        await asyncio.sleep(0.04)
        assert await admit(two) == 429
        assert await a.client.pttl(key) < ttl
        assert await admit(two, other) == 200
        assert await admit(two, user, "resume") == 200
        await asyncio.sleep(1.05)
        assert await admit(two) == 200
        for broken in ("not-a-number", "-1", "01", "1e2", "1000000001"):
            await a.client.set(key, broken, ex=10)
            assert await admit(one) == 503
            assert await a.client.get(key) == broken
        await a.client.delete(key)
        await a.client.hset(key, "wrong", "type")
        assert await admit(one) == 503
        await a.client.delete(key)
        await a.client.set(key, "10")  # repair an orphaned counter's missing expiry
        assert await admit(one) == 429
        assert 0 < await a.client.pttl(key) <= 1000
    finally:
        keys = [key async for key in a.client.scan_iter(match=prefix + ":*")]
        if keys:
            await a.client.delete(*keys)
        await a.close()
        await b.close()
