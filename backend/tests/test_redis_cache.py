import asyncio
import json
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.redis_client import RedisRuntime, RedisUnavailableError
from app.main import app
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.cache import taxonomy as cache_module
from app.modules.cache.taxonomy import TaxonomyCache
from app.modules.documents import taxonomy_router, taxonomy_service
from app.modules.documents.taxonomy_service import LoadedTaxonomy

GROUPS = [{"parent": "Housing", "children": ["Social housing"], "source_ref": None}]


class MemoryRedis:
    def __init__(self):
        self.data = {}
        self.writes = 0
        self.error_on = None

    async def get(self, key):
        if self.error_on == "get":
            raise RedisConnectionError("test offline")
        return self.data.get(key)

    async def set(self, key, value, **kwargs):
        if self.error_on == "set":
            raise RedisConnectionError("test offline")
        self.data[key] = value
        self.writes += 1

    async def delete(self, key):
        if self.error_on == "delete":
            raise RedisConnectionError("test offline")
        self.data.pop(key, None)


def fixture_cache(monkeypatch, **options):
    runtime = RedisRuntime()
    runtime.settings = Settings(_env_file=None, redis_enabled=True, **options)
    runtime.client = MemoryRedis()
    monkeypatch.setattr(cache_module, "load_taxonomy_tree", lambda: LoadedTaxonomy(GROUPS, True))
    return TaxonomyCache(runtime), runtime


async def test_disabled_redis_never_connects():
    runtime = RedisRuntime()
    await runtime.start(Settings(_env_file=None))
    assert runtime.client is None
    with pytest.raises(RedisUnavailableError):
        await runtime.execute(lambda client: client.ping())
    await runtime.close()


def test_invalid_redis_budget_and_prefix_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_operation_budget_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_key_prefix="not a valid prefix")


async def test_miss_hit_invalidation_and_disabled_baseline(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)
    first, status = await cache.read()
    assert status == "MISS"
    assert first == {"groups": GROUPS}
    assert await cache.read() == (first, "HIT")
    assert runtime.snapshot()["counters"]["taxonomy_loader_calls"] == 1
    await cache.invalidate()
    assert (await cache.read())[1] == "MISS"
    runtime.settings = runtime.settings.model_copy(update={"taxonomy_cache_enabled": False})
    assert (await cache.read())[1] == "BYPASS"
    assert runtime.snapshot()["counters"]["taxonomy_loader_calls"] == 3


async def test_cold_requests_coalesce_in_one_process(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)

    def slow_loader():
        time.sleep(0.03)
        return LoadedTaxonomy(GROUPS, True)

    monkeypatch.setattr(cache_module, "load_taxonomy_tree", slow_loader)
    results = await asyncio.gather(*(cache.read() for _ in range(20)))
    assert all(payload == {"groups": GROUPS} for payload, _ in results)
    assert runtime.snapshot()["counters"]["taxonomy_loader_calls"] == 1


async def test_fallback_is_not_cached(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)
    monkeypatch.setattr(cache_module, "load_taxonomy_tree", lambda: LoadedTaxonomy(GROUPS, False))
    assert (await cache.read())[1] == "BYPASS-FALLBACK"
    assert (await cache.read())[1] == "BYPASS-FALLBACK"
    assert runtime.client.writes == 0
    assert runtime.snapshot()["counters"]["taxonomy_loader_calls"] == 2


@pytest.mark.parametrize("value", ["{broken", '{"groups": 3}', '{"groups": []'])
async def test_bad_json_or_schema_rebuilds(monkeypatch, value):
    cache, runtime = fixture_cache(monkeypatch)
    runtime.client.data[cache.key] = value
    assert (await cache.read())[0] == {"groups": GROUPS}
    assert runtime.snapshot()["counters"]["taxonomy_cache_invalid"] >= 1


async def test_oversize_result_is_not_stored(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch, taxonomy_cache_max_bytes=1024)
    large = [{"parent": "Housing", "children": ["x" * 2000]}]
    monkeypatch.setattr(cache_module, "load_taxonomy_tree", lambda: LoadedTaxonomy(large, True))
    await cache.read()
    assert runtime.client.writes == 0


async def test_invalid_utf8_rebuilds_from_authority(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)

    async def invalid(_key):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid test cache")

    runtime.client.get = invalid
    payload, _status = await cache.read()
    assert payload == {"groups": GROUPS}
    assert runtime.snapshot()["counters"]["taxonomy_cache_invalid"] >= 1


async def test_coalescing_wait_is_bounded(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch, taxonomy_cache_wait_seconds=0.01)
    cache._lock = asyncio.Lock()
    await cache._lock.acquire()
    try:
        payload, status = await cache.read()
        assert payload == {"groups": GROUPS} and status == "BYPASS"
        assert runtime.snapshot()["counters"]["taxonomy_coalescing_timeouts"] == 1
    finally:
        cache._lock.release()


async def test_redis_failure_bypasses_without_retrying_get(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)
    runtime.client.error_on = "get"
    payload, status = await cache.read()
    assert payload == {"groups": GROUPS} and status == "BYPASS"
    assert runtime.status == "degraded"
    assert runtime.snapshot()["counters"]["redis_operations"] == 1
    assert runtime.client.writes == 0


async def test_cache_write_or_invalidation_failure_does_not_fail_business(monkeypatch):
    cache, runtime = fixture_cache(monkeypatch)
    runtime.client.error_on = "set"
    assert (await cache.read())[0] == {"groups": GROUPS}
    runtime.client.error_on = "delete"
    await cache.invalidate()
    assert runtime.snapshot()["counters"]["taxonomy_invalidation_errors"] == 1


async def test_operation_budget_cancels_wait_without_retry():
    runtime = RedisRuntime()
    runtime.settings = Settings(_env_file=None, redis_operation_budget_seconds=0.02)
    runtime.client = MemoryRedis()
    started = time.monotonic()
    calls = 0

    async def blocked(_client):
        nonlocal calls
        calls += 1
        await asyncio.sleep(10)

    with pytest.raises(RedisUnavailableError):
        await runtime.execute(blocked)
    assert calls == 1 and time.monotonic() - started < 0.5


def test_db_fallback_provenance_and_write_returns_saved_values(monkeypatch):
    def unavailable():
        raise OSError("database offline")

    monkeypatch.setattr(taxonomy_service.taxonomy_repository, "is_empty", unavailable)
    assert not taxonomy_service.load_taxonomy_tree().cacheable
    monkeypatch.setattr(taxonomy_service.taxonomy_repository, "replace_tree", lambda groups: None)
    assert taxonomy_service.replace_taxonomy_tree(GROUPS) == GROUPS


def test_cache_is_after_auth_and_admin_status_is_protected(monkeypatch):
    read = AsyncMock(return_value=({"groups": GROUPS}, "HIT"))
    monkeypatch.setattr(taxonomy_router.taxonomy_cache, "read", read)
    with TestClient(app) as client:
        assert client.get("/api/v1/taxonomy").status_code == 401
        read.assert_not_awaited()
        assert client.get("/api/v1/admin/redis").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: {"id": "reader", "role": "user"}
        try:
            response = client.get("/api/v1/taxonomy")
            assert response.json() == {"groups": GROUPS}
            assert response.headers["X-Cache"] == "HIT"
            assert client.get("/api/v1/admin/redis").status_code == 403
        finally:
            app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[require_admin] = lambda: {"id": "admin", "role": "admin"}
        try:
            body = client.get("/api/v1/admin/redis").json()
            assert body["scope"] == "per_process"
            assert "redis_url" not in json.dumps(body)
        finally:
            app.dependency_overrides.pop(require_admin, None)


@pytest.mark.integration
async def test_real_redis_expiry_and_cross_client_invalidation(monkeypatch):
    import os

    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to a disposable Redis instance.")
    settings = Settings(
        _env_file=None,
        redis_enabled=True,
        redis_url=url,
        redis_key_prefix="policy:test:" + uuid4().hex,
        taxonomy_cache_ttl_seconds=1,
    )
    a, b = RedisRuntime(), RedisRuntime()
    await a.start(settings)
    await b.start(settings)
    cache_a, cache_b = TaxonomyCache(a), TaxonomyCache(b)
    monkeypatch.setattr(cache_module, "load_taxonomy_tree", lambda: LoadedTaxonomy(GROUPS, True))
    try:
        assert a.status == b.status == "healthy"
        assert (await cache_a.read())[1] == "MISS"
        assert (await cache_b.read())[1] == "HIT"
        assert 0 < await a.client.ttl(cache_a.key) <= 1
        await asyncio.sleep(1.05)
        assert (await cache_b.read())[1] == "MISS"
        changed = [{"parent": "Energy", "children": ["Clean power"], "source_ref": None}]
        monkeypatch.setattr(
            cache_module, "load_taxonomy_tree", lambda: LoadedTaxonomy(changed, True)
        )
        await cache_a.invalidate()
        assert (await cache_b.read())[0] == {"groups": changed}
    finally:
        if a.client is not None:
            await a.client.delete(cache_a.key)
        await a.close()
        await b.close()
