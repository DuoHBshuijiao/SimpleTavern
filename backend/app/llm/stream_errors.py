"""流式响应里的两类错误：上游在流中报的错，和已建立连接后中途断开（P2-6）。

- 上游错误：各协议都会在流里发 ``error`` 对象（OpenAI 兼容的 ``{"error": {...}}``、Responses 的 ``error`` 事件、
  Anthropic 的 ``event: error``、Gemini 的 ``{"error": {"code", "status"}}``）。这里按状态码、type、code 映射到统一错误，
  并在 message 里保留上游原话，不再换成笼统的解析错误。
- 中途断开：连接已经建立后断开，和一开始就连不上（``upstream_unreachable``）不是一回事，统一报 ``stream_interrupted``，
  并说明是否已经收到部分内容。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable

import httpx

from app.errors import AppError

_MAX_UPSTREAM_MESSAGE_CHARS = 300
_AUTH_HINTS = ("auth", "invalid_api_key", "permission", "unauthenticated", "forbidden")
_QUOTA_HINTS = ("rate_limit", "quota", "resource_exhausted", "too_many_requests", "insufficient")
_RETRYABLE_HINTS = ("overloaded", "server_error", "internal", "unavailable", "timeout", "api_error")


def _status_of(err: dict[str, Any]) -> int | None:
    for key in ("status", "code", "http_status", "status_code"):
        value = err.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 100 <= value < 600:
            return value
        if isinstance(value, str) and value.isdigit() and 100 <= int(value) < 600:
            return int(value)
    return None


def upstream_stream_error(err: Any, *, source: str, provider: str | None, protocol: str | None) -> AppError:
    """把流里的上游错误对象转成统一错误，message 保留上游原话（AppError 会照常打码）。"""
    data = err if isinstance(err, dict) else {"message": str(err or "")}
    upstream_message = str(data.get("message") or data.get("error_description") or "").strip()
    labels = [str(data[k]) for k in ("type", "code", "status") if data.get(k) not in (None, "")]
    hints = " ".join(labels).lower()
    status = _status_of(data)
    shown = (upstream_message or " / ".join(labels) or "未给出说明")[:_MAX_UPSTREAM_MESSAGE_CHARS]
    # 上游错误码写成「错误码 xxx」：现有的 code= 打码规则（针对 OAuth 授权码）会把它整个换成 ***
    parts = [f"type={data['type']}"] if data.get("type") not in (None, "") else []
    if data.get("code") not in (None, ""):
        parts.append(f"错误码 {data['code']}")
    parts += [f"{k}={data[k]}" for k in ("status", "param") if data.get(k) not in (None, "")]
    detail = "; ".join(parts)
    common: dict[str, Any] = {
        "source": source,
        "provider": provider,
        "protocol": protocol,
        "upstream_status": status,
        "detail": (detail + "; " if detail else "") + f"message={upstream_message or '(empty)'}",
    }
    if status in (401, 403) or any(h in hints for h in _AUTH_HINTS):
        return AppError(
            code="provider_auth_failed",
            message=f"上游在流中返回鉴权错误：{shown}",
            status_code=403 if status == 403 else 401,
            suggested_action="检查 API Key、账号权限和所选 API 预设",
            **common,
        )
    if status == 429 or any(h in hints for h in _QUOTA_HINTS):
        return AppError(
            code="provider_quota_exceeded",
            message=f"上游在流中返回额度或限流错误：{shown}",
            status_code=429,
            retryable=True,
            suggested_action="检查账户额度，或稍后重试",
            **common,
        )
    retryable = (status is not None and status >= 500) or any(h in hints for h in _RETRYABLE_HINTS)
    return AppError(
        code="upstream_request_failed",
        message=f"上游在流中返回错误：{shown}",
        status_code=502,
        retryable=retryable,
        suggested_action="根据上游说明调整请求，或稍后重试",
        **common,
    )


def stream_interrupted_error(
    exc: BaseException,
    *,
    partial: bool,
    source: str,
    provider: str | None,
    protocol: str | None,
) -> AppError:
    """连接建立后中途断开。复用错误体系里已有的 ``stream_interrupted``。"""
    message = "上游连接在传输中断开，已收到部分内容" if partial else "上游连接在返回内容前断开"
    return AppError(
        code="stream_interrupted",
        message=message,
        detail=f"{type(exc).__name__}: {exc}",
        source=source,
        status_code=502,
        retryable=True,
        provider=provider,
        protocol=protocol,
        suggested_action="已收到的内容会保留；可以重试或继续生成" if partial else "稍后重试，并检查网络或上游服务状态",
    )


async def guarded_lines(
    response: httpx.Response,
    *,
    partial: Callable[[], bool],
    source: str,
    provider: str | None,
    protocol: str | None,
) -> AsyncIterator[str]:
    """``response.aiter_lines()``，读取中断开时转成 ``stream_interrupted``；超时照旧交给统一映射。"""
    lines = response.aiter_lines()
    while True:
        try:
            line = await lines.__anext__()
        except StopAsyncIteration:
            return
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as exc:
            raise stream_interrupted_error(
                exc, partial=partial(), source=source, provider=provider, protocol=protocol
            ) from exc
        yield line
