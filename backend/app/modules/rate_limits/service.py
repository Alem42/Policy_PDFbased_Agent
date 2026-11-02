"""Shared fixed-window admission. PostgreSQL still owns tasks and chat state."""

from dataclasses import dataclass
from math import ceil
from typing import Literal
from uuid import UUID

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.redis_client import RedisRuntime, RedisUnavailableError, redis_runtime

Rule = Literal["chat", "resume", "upload", "demo"]

# A single Redis operation prevents two API processes from admitting the same slot.
# Rejections never increment the counter or extend the window. Validate before writes:
# Redis scripts are atomic, but an error does not roll back earlier script writes.
ADMISSION_LUA = """
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
if not limit or limit < 1 or limit ~= math.floor(limit)
   or not window or window < 1 or window ~= math.floor(window) then
    return redis.error_reply('invalid admission configuration')
end
local raw = redis.call('GET', KEYS[1])
local current = 0
if raw then current = tonumber(raw) end
if not current or current < 0 or current ~= math.floor(current) or current > 1000000000
   or (raw and raw ~= tostring(current)) then
    return redis.error_reply('invalid admission counter')
end
local ttl = redis.call('PTTL', KEYS[1])
if ttl == -1 then
    redis.call('PEXPIRE', KEYS[1], window)
    ttl = window
end
if current >= limit then
    return {0, 0, math.max(ttl, 0)}
end
local count = redis.call('INCR', KEYS[1])
if count == 1 or ttl < 0 then
    redis.call('PEXPIRE', KEYS[1], window)
end
return {1, limit - count, redis.call('PTTL', KEYS[1])}
"""


@dataclass(frozen=True)
class Admission:
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    def __init__(self, runtime: RedisRuntime):
        self.runtime = runtime

    async def enforce(self, user_id: str, rule: Rule) -> Admission | None:
        settings = self.runtime.settings or get_settings()
        if not settings.rate_limit_enabled:
            return None
        limits = {
            "chat": settings.rate_limit_chat_limit,
            "resume": settings.rate_limit_resume_limit,
            "upload": settings.rate_limit_upload_limit,
            "demo": settings.redis_demo_limit,
        }
        limit = limits[rule]
        # Only authenticated server-side IDs, never a caller-supplied IP/header.
        key = f"{settings.redis_key_prefix}:rl:v1:{rule}:user:{UUID(user_id)}"
        try:
            result = await self.runtime.execute(
                lambda client: client.eval(
                    ADMISSION_LUA, 1, key, limit, settings.rate_limit_window_seconds * 1000
                )
            )
            if (
                not isinstance(result, (list, tuple))
                or len(result) != 3
                or any(type(value) is not int for value in result)
                or result[0] not in (0, 1)
                or not 0 <= result[1] < limit
                or result[2] < 0
            ):
                raise ValueError("Invalid admission response")
        except (RedisUnavailableError, ValueError, UnicodeError) as exc:
            self.runtime.count(f"rate_{rule}_errors")
            # Unknown command outcome must not trigger an automatic second debit.
            raise HTTPException(
                status_code=503,
                detail="Admission service temporarily unavailable. Please try again later.",
                headers={"Retry-After": "1"},
            ) from exc
        retry_after = max(1, ceil(result[2] / 1000))
        if result[0] == 0:
            self.runtime.count(f"rate_{rule}_denied")
            raise HTTPException(
                status_code=429,
                detail=f"Too many {rule} requests. Please retry after the current window.",
                headers={"Retry-After": str(retry_after)},
            )
        self.runtime.count(f"rate_{rule}_allowed")
        return Admission(remaining=result[1], retry_after_seconds=retry_after)


rate_limiter = RateLimiter(redis_runtime)
