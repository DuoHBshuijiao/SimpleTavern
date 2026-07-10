from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.errors import AppError, as_app_error


def sse_event(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(dict(data), ensure_ascii=False)}\n\n"


def sse_meta(
    *,
    request_id: str,
    provider: str | None = None,
    protocol: str | None = None,
    resolved_model: str | None = None,
) -> str:
    payload: dict[str, Any] = {"requestId": request_id}
    if provider:
        payload["provider"] = provider
    if protocol:
        payload["protocol"] = protocol
    if resolved_model:
        payload["resolvedModel"] = resolved_model
    return sse_event("meta", payload)


def sse_done(data: Mapping[str, Any]) -> str:
    return sse_event("done", data)


def sse_terminal_error(
    exc: BaseException,
    *,
    request_id: str,
    source: str,
    default_code: str = "stream_failed",
    default_message: str = "流式请求失败",
    provider: str | None = None,
    protocol: str | None = None,
) -> str:
    error = as_app_error(
        exc,
        source=source,
        default_code=default_code,
        default_message=default_message,
        provider=provider,
        protocol=protocol,
    )
    payload = error.to_dict(request_id)
    payload["terminal"] = True
    return sse_event("error", payload)


def app_error_sse(error: AppError, *, request_id: str) -> str:
    payload = error.to_dict(request_id)
    payload["terminal"] = True
    return sse_event("error", payload)
