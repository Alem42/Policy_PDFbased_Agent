"""Cap how many chat turns run at once in this process, streams included.

Rate limits bound how often each user asks; this bounds how many model-backed
turns a small server runs simultaneously. A request waits briefly for a free
slot, then receives 503 with Retry-After instead of piling up.
"""

import asyncio
import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class TurnLimit:
    """Shared counters, so the admin status endpoint can read what the middleware sees."""

    def __init__(self, limit: int, wait_seconds: float) -> None:
        self.limit = limit
        self.wait_seconds = wait_seconds
        self.active = 0
        self.waiting = 0
        self.rejected = 0
        self._slots: asyncio.Semaphore | None = None

    def snapshot(self) -> dict:
        return {
            "scope": "per_process",
            "limit": self.limit,
            "active": self.active,
            "waiting": self.waiting,
            "rejected": self.rejected,
        }

    async def acquire(self) -> bool:
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.limit)
        self.waiting += 1
        try:
            async with asyncio.timeout(self.wait_seconds):
                await self._slots.acquire()
        except TimeoutError:
            self.rejected += 1
            logger.warning("Chat concurrency limit reached: %s", self.snapshot())
            return False
        finally:
            self.waiting -= 1
        self.active += 1
        return True

    def release(self) -> None:
        self.active -= 1
        self._slots.release()


class ConcurrencyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, paths: set[str], limit: TurnLimit) -> None:
        self.app = app
        self.paths = {path.rstrip("/") for path in paths}
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") not in self.paths
        ):
            await self.app(scope, receive, send)
            return
        if not await self.limit.acquire():
            response = JSONResponse(
                {"detail": "The assistant is busy. Please try again shortly."},
                status_code=503,
                headers={"Retry-After": "5"},
            )
            await response(scope, receive, send)
            return
        try:
            # For streaming responses this returns only after the last event is sent
            # or the client disconnects, so the slot covers the whole answer.
            await self.app(scope, receive, send)
        finally:
            self.limit.release()


def _from_settings() -> TurnLimit:
    from app.core.config import get_settings

    settings = get_settings()
    return TurnLimit(settings.chat_max_concurrent_turns, settings.chat_queue_wait_seconds)


chat_turn_limit = _from_settings()
