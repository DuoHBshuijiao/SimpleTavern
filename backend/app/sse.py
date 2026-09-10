from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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
    warnings: list[dict[str, Any]] | None = None,
    protocol_resolution: Mapping[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {"requestId": request_id}
    if provider:
        payload["provider"] = provider
    if protocol:
        payload["protocol"] = protocol
    if resolved_model:
        payload["resolvedModel"] = resolved_model
    if warnings:
        payload["warnings"] = list(warnings)
    if protocol_resolution:
        # T-822：auto 协议 / 深度 clamp / Fast / 缓存计划的可见结果
        payload["protocolResolution"] = dict(protocol_resolution)
        cache = protocol_resolution.get("cache")
        if isinstance(cache, Mapping):
            # T-821：顶层 meta.cache，前端徽标不必再钻 protocolResolution
            payload["cache"] = dict(cache)
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
    enrich: Callable[[AppError], AppError] | None = None,
) -> str:
    """把异常转成终态 error 事件；``enrich`` 可按请求上下文补 suggestedAction / action（T-822 思考回传按钮等）。"""
    error = as_app_error(
        exc,
        source=source,
        default_code=default_code,
        default_message=default_message,
        provider=provider,
        protocol=protocol,
    )
    if enrich is not None:
        try:
            error = enrich(error) or error
        except Exception:  # noqa: BLE001 - 补充信息失败不能吞掉原错误
            pass
    payload = error.to_dict(request_id)
    payload["terminal"] = True
    return sse_event("error", payload)


def app_error_sse(error: AppError, *, request_id: str) -> str:
    payload = error.to_dict(request_id)
    payload["terminal"] = True
    return sse_event("error", payload)
