from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class MaxBodySizeMiddleware:
    """Rejects requests whose Content-Length exceeds max_bytes before the body
    is read, so an oversized payload never reaches JSON parsing."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None and int(content_length) > self.max_bytes:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": "payload_too_large",
                    "detail": f"request body överskrider maxgränsen på {self.max_bytes} bytes",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
