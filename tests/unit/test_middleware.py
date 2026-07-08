from app.middleware import MaxBodySizeMiddleware


class _DummyApp:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True


def _http_scope(content_length: int | None) -> dict:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "headers": headers}


async def test_request_under_limit_passes_through() -> None:
    inner = _DummyApp()
    middleware = MaxBodySizeMiddleware(inner, max_bytes=1000)

    await middleware(_http_scope(500), None, None)

    assert inner.called is True


async def test_request_over_limit_is_rejected_with_413() -> None:
    inner = _DummyApp()
    middleware = MaxBodySizeMiddleware(inner, max_bytes=1000)
    sent_messages = []

    async def send(message) -> None:
        sent_messages.append(message)

    await middleware(_http_scope(5000), None, send)

    assert inner.called is False
    start = next(m for m in sent_messages if m["type"] == "http.response.start")
    assert start["status"] == 413


async def test_request_without_content_length_passes_through() -> None:
    inner = _DummyApp()
    middleware = MaxBodySizeMiddleware(inner, max_bytes=1000)

    await middleware(_http_scope(None), None, None)

    assert inner.called is True


async def test_non_http_scope_passes_through_untouched() -> None:
    inner = _DummyApp()
    middleware = MaxBodySizeMiddleware(inner, max_bytes=1000)

    await middleware({"type": "lifespan"}, None, None)

    assert inner.called is True
