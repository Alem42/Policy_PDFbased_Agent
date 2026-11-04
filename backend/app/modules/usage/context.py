"""Who and what a paid API call is for, carried through async tasks and threads.

asyncio tasks and asyncio.to_thread copy the current context automatically; plain
ThreadPoolExecutor.submit does not, so those call sites wrap their work with
`bind(...)`.
"""

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class UsageScope:
    area: str = "unknown"
    operation: str = "unknown"
    user_id: str | None = None
    # From the bearer token (no database lookup per request); resolved when recorded.
    user_uid: str | None = None
    session_id: str | None = None
    document_id: str | None = None


# UsageScope is frozen, so sharing one default instance is safe.
_scope: ContextVar[UsageScope] = ContextVar("api_usage_scope", default=UsageScope())  # noqa: B039


def current() -> UsageScope:
    return _scope.get()


@contextmanager
def usage_scope(**fields):
    """Refine the current scope (unset fields are inherited from the caller)."""
    token = _scope.set(replace(_scope.get(), **{k: v for k, v in fields.items() if v is not None}))
    try:
        yield
    finally:
        _scope.reset(token)


def set_scope(**fields) -> None:
    """Replace fields for the rest of the current task (used by the HTTP middleware)."""
    _scope.set(replace(_scope.get(), **fields))


def bind(function):
    """Run `function` later in another thread with the caller's scope."""
    context = copy_context()
    return lambda *args, **kwargs: context.run(function, *args, **kwargs)
