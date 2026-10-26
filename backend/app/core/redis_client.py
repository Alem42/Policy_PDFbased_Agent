"""Per-process async Redis client. Cache failures never become unbounded waits."""

import asyncio
from collections import Counter
from threading import Lock
from time import perf_counter

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings


class RedisUnavailableError(RuntimeError):
    pass


class RedisRuntime:
    def __init__(self):
        self.client: Redis | None = None
        self.settings: Settings | None = None
        self.status = "disabled"
        self._counters = Counter()
        self._lock = Lock()

    def count(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    async def start(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        with self._lock:
            self._counters.clear()
        if not self.settings.redis_enabled:
            self.status = "disabled"
            return
        self.client = Redis.from_url(
            self.settings.redis_url,
            decode_responses=True,
            max_connections=self.settings.redis_max_connections,
            socket_connect_timeout=self.settings.redis_connect_timeout_seconds,
            socket_timeout=self.settings.redis_socket_timeout_seconds,
            retry=Retry(NoBackoff(), 0),
            health_check_interval=0,
        )
        await self.probe()

    async def execute(self, operation):
        if self.client is None or self.settings is None:
            raise RedisUnavailableError("Redis is disabled.")
        started = perf_counter()
        self.count("redis_operations")
        try:
            async with asyncio.timeout(self.settings.redis_operation_budget_seconds):
                result = await operation(self.client)
            self.status = "healthy"
            return result
        except (RedisError, TimeoutError, OSError) as exc:
            self.status = "degraded"
            self.count("redis_errors")
            raise RedisUnavailableError("Redis is temporarily unavailable.") from exc
        finally:
            self.count("redis_operation_microseconds", round((perf_counter() - started) * 1e6))

    async def probe(self) -> None:
        if self.client is not None:
            try:
                await self.execute(lambda client: client.ping())
            except RedisUnavailableError:
                pass

    async def close(self) -> None:
        client, self.client = self.client, None
        try:
            if client is not None:
                await client.aclose()
        finally:
            self.status = "disabled"

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
        return {
            "scope": "per_process",
            "status": self.status,
            "enabled": bool(self.settings and self.settings.redis_enabled),
            "cache_enabled": bool(self.settings and self.settings.taxonomy_cache_enabled),
            "counters": {"taxonomy_loader_calls": 0, **counters},
            "limits": {
                "max_connections": self.settings.redis_max_connections if self.settings else 0,
                "operation_budget_seconds": (
                    self.settings.redis_operation_budget_seconds if self.settings else 0
                ),
            },
        }


redis_runtime = RedisRuntime()
