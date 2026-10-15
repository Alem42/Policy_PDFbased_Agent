"""Reject oversized upload requests before/during multipart parsing."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class UploadBodyLimitMiddleware:
    """Bound the one-file upload body, including multipart fields and overhead."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        upload_path: str,
        max_file_bytes: int,
        overhead_bytes: int,
    ) -> None:
        self.app = app
        self.upload_path = upload_path.rstrip("/")
        self.max_body_bytes = max_file_bytes + overhead_bytes
        self.detail = (
            f"Upload request is too large. Maximum file size is {max_file_bytes} bytes "
            f"({max_file_bytes / (1024 * 1024):g} MiB)."
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != self.upload_path
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        if b"content-length" in headers:
            try:
                content_length = int(headers[b"content-length"])
                if content_length < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)(
                    scope, receive, send
                )
                return
            if content_length > self.max_body_bytes:
                await JSONResponse({"detail": self.detail}, status_code=413)(scope, receive, send)
                return

        received = 0
        exceeded = False
        rejection_sent = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    exceeded = True
                    # Multipart parsers close their spooled files on this error.
                    # FastAPI may translate it to 400; limited_send supplies 413.
                    raise MultiPartException(self.detail)
            return message

        async def limited_send(message: Message) -> None:
            nonlocal rejection_sent
            if not exceeded:
                await send(message)
            elif not rejection_sent:
                rejection_sent = True
                await JSONResponse({"detail": self.detail}, status_code=413)(scope, receive, send)

        try:
            await self.app(scope, limited_receive, limited_send)
        except MultiPartException:
            if not exceeded:
                raise
            if not rejection_sent:
                await JSONResponse({"detail": self.detail}, status_code=413)(scope, receive, send)
