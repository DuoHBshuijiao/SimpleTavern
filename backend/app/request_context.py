from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send


REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def normalize_client_request_id(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate or not _REQUEST_ID_PATTERN.fullmatch(candidate):
        return None
    return candidate


def get_request_id(default: str | None = None) -> str | None:
    return _request_id_var.get() or default


class RequestIdMiddleware:
    """为整个 ASGI 请求（包括流式响应）绑定并回传 requestId。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_id: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"x-request-id":
                incoming_id = raw_value.decode("latin-1")
                break
        request_id = normalize_client_request_id(incoming_id) or new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(name, value) for name, value in headers if name.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id_var.reset(token)
