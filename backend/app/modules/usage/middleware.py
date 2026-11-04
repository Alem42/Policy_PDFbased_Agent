"""Tag each HTTP request with its feature area and signed-in user for the usage ledger."""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.modules.auth.service import decode_access_token
from app.modules.usage.context import set_scope

# Longest prefix first; paths are relative to the API prefix.
AREAS = (
    ("/chat", "chat", "answer"),
    ("/admin/evaluation", "evaluation", "request"),
    ("/admin/documents", "documents", "request"),
    ("/admin/embedding", "settings", "connection_test"),
    ("/admin/reranking", "settings", "connection_test"),
    ("/admin/web-search", "settings", "request"),
    ("/documents", "library", "request"),
)


class UsageScopeMiddleware:
    def __init__(self, app: ASGIApp, *, prefix: str) -> None:
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope["path"].removeprefix(self.prefix)
            area, operation = next(
                ((a, o) for prefix, a, o in AREAS if path.startswith(prefix)), ("api", "request")
            )
            uid = None
            for name, value in scope.get("headers", []):
                if name == b"authorization" and value.startswith(b"Bearer "):
                    try:
                        uid = decode_access_token(value[7:].decode().strip())["sub"]
                    except (ValueError, KeyError, UnicodeDecodeError):
                        uid = None
                    break
            # Each request runs in its own task, so this does not leak between requests.
            set_scope(area=area, operation=operation, user_uid=uid)
        await self.app(scope, receive, send)
