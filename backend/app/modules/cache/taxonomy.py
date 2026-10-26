"""Cache only DB-backed taxonomy results; authentication remains in the route."""

import asyncio
import json
import random

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.redis_client import RedisRuntime, RedisUnavailableError, redis_runtime
from app.modules.documents.taxonomy_schemas import TaxonomyResponse
from app.modules.documents.taxonomy_service import load_taxonomy_tree


class TaxonomyCache:
    def __init__(self, runtime: RedisRuntime):
        self.runtime = runtime
        self._lock: asyncio.Lock | None = None

    def reset(self):
        self._lock = None

    @property
    def settings(self):
        return self.runtime.settings or get_settings()

    @property
    def key(self):
        return f"{self.settings.redis_key_prefix}:cache:taxonomy:v1"

    async def _load(self):
        self.runtime.count("taxonomy_loader_calls")
        loaded = await asyncio.to_thread(load_taxonomy_tree)
        payload = TaxonomyResponse(groups=loaded.groups).model_dump(mode="json")
        if not loaded.cacheable:
            self.runtime.count("taxonomy_fallbacks")
        return payload, loaded.cacheable

    async def _lookup(self):
        try:
            raw = await self.runtime.execute(lambda client: client.get(self.key))
        except RedisUnavailableError:
            return None, "BYPASS"
        except UnicodeError:
            self.runtime.count("taxonomy_cache_invalid")
            return None, "MISS"
        if raw is not None:
            try:
                if len(raw.encode("utf-8")) > self.settings.taxonomy_cache_max_bytes:
                    raise ValueError("Cached taxonomy exceeds size budget")
                payload = TaxonomyResponse.model_validate_json(raw).model_dump(mode="json")
                self.runtime.count("taxonomy_cache_hits")
                return payload, "HIT"
            except (ValidationError, ValueError, TypeError):
                self.runtime.count("taxonomy_cache_invalid")
        return None, "MISS"

    async def read(self):
        if not self.settings.redis_enabled or not self.settings.taxonomy_cache_enabled:
            self.runtime.count("taxonomy_cache_bypass")
            payload, cacheable = await self._load()
            return payload, "BYPASS" if cacheable else "BYPASS-FALLBACK"
        payload, status = await self._lookup()
        if payload is not None:
            return payload, status
        if status == "BYPASS":
            self.runtime.count("taxonomy_cache_bypass")
            payload, cacheable = await self._load()
            return payload, status if cacheable else "BYPASS-FALLBACK"
        if self._lock is None:
            self._lock = asyncio.Lock()
        # One tiny taxonomy loader per process on a cold key. This is not a
        # cross-process distributed lock; TTL/invalidation provide cache freshness.
        try:
            async with asyncio.timeout(self.settings.taxonomy_cache_wait_seconds):
                await self._lock.acquire()
        except TimeoutError:
            self.runtime.count("taxonomy_coalescing_timeouts")
            payload, cacheable = await self._load()
            return payload, "BYPASS" if cacheable else "BYPASS-FALLBACK"
        try:
            payload, status = await self._lookup()
            if payload is not None:
                self.runtime.count("taxonomy_cache_coalesced")
                return payload, status
            self.runtime.count("taxonomy_cache_misses")
            payload, cacheable = await self._load()
            if not cacheable:
                return payload, "BYPASS-FALLBACK"
            encoded = json.dumps(payload, ensure_ascii=False)
            if (
                status != "BYPASS"
                and len(encoded.encode()) <= self.settings.taxonomy_cache_max_bytes
            ):
                ttl = self.settings.taxonomy_cache_ttl_seconds
                ttl += random.randint(0, max(0, ttl // 10))
                try:
                    await self.runtime.execute(lambda client: client.set(self.key, encoded, ex=ttl))
                    self.runtime.count("taxonomy_cache_writes")
                except RedisUnavailableError:
                    status = "BYPASS"
            return payload, status
        finally:
            self._lock.release()

    async def invalidate(self):
        if not self.settings.redis_enabled:
            return
        try:
            await self.runtime.execute(lambda client: client.delete(self.key))
            self.runtime.count("taxonomy_invalidations")
        except RedisUnavailableError:
            self.runtime.count("taxonomy_invalidation_errors")


taxonomy_cache = TaxonomyCache(redis_runtime)
