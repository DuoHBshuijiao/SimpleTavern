from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.request_context import REQUEST_ID_HEADER, get_request_id, new_request_id


logger = logging.getLogger(__name__)
_MAX_DETAIL_CHARS = 2000
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)([^\s,;]+)"),
    re.compile(r"""(?i)(["']?(?:api[-_]?key|access[-_]?token|token|secret|cookie)["']?\s*[:=]\s*["']?)([^"'\s,;}]+)"""),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def redact_sensitive_text(value: Any, *, max_chars: int = _MAX_DETAIL_CHARS) -> str:
    text = str(value or "")
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(r"\1***", text)
        else:
            text = pattern.sub("***", text)
    if len(text) > max_chars:
        text = f"{text[:max_chars]}...[truncated]"
    return text


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    detail: str | None = None
    source: str
    retryable: bool = False
    request_id: str = Field(alias="requestId")
    provider: str | None = None
    protocol: str | None = None
    upstream_status: int | None = Field(default=None, alias="upstreamStatus")
    suggested_action: str | None = Field(default=None, alias="suggestedAction")


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        source: str,
        status_code: int = 500,
        detail: str | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        provider: str | None = None,
        protocol: str | None = None,
        upstream_status: int | None = None,
        suggested_action: str | None = None,
    ) -> None:
        safe_message = redact_sensitive_text(message)
        super().__init__(safe_message)
        self.code = code
        self.message = safe_message
        self.source = source
        self.status_code = status_code
        self.detail = redact_sensitive_text(detail) if detail else None
        self.retryable = retryable
        self.request_id = request_id
        self.provider = provider
        self.protocol = protocol
        self.upstream_status = upstream_status
        self.suggested_action = suggested_action

    def to_envelope(self, request_id: str | None = None) -> ErrorEnvelope:
        resolved_request_id = self.request_id or request_id or get_request_id()
        if not resolved_request_id:
            resolved_request_id = "req_unavailable"
        return ErrorEnvelope(
            code=self.code,
            message=self.message,
            detail=self.detail,
            source=self.source,
            retryable=self.retryable,
            requestId=resolved_request_id,
            provider=self.provider,
            protocol=self.protocol,
            upstreamStatus=self.upstream_status,
            suggestedAction=self.suggested_action,
        )

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        return self.to_envelope(request_id).model_dump(by_alias=True, exclude_none=True)


def _request_id_from_request(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or get_request_id()


def _upstream_detail(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    raw = (response.text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return redact_sensitive_text(raw)
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return redact_sensitive_text(message)
        if isinstance(error, str) and error.strip():
            return redact_sensitive_text(error)
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return redact_sensitive_text(message)
    return redact_sensitive_text(raw)


def as_app_error(
    exc: BaseException,
    *,
    source: str,
    default_code: str = "internal_error",
    default_message: str = "操作失败",
    default_status_code: int = 500,
    provider: str | None = None,
    protocol: str | None = None,
) -> AppError:
    if isinstance(exc, AppError):
        return exc

    common = {
        "source": source,
        "provider": provider,
        "protocol": protocol,
    }
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _upstream_detail(exc.response) or redact_sensitive_text(exc)
        if status in (401, 403):
            return AppError(
                code="provider_auth_failed",
                message="上游服务鉴权失败",
                status_code=401 if status == 401 else 403,
                detail=detail,
                retryable=False,
                upstream_status=status,
                suggested_action="检查 API Key、账号权限和所选 API 预设",
                **common,
            )
        if status == 429:
            return AppError(
                code="provider_quota_exceeded",
                message="上游服务额度不足或请求过于频繁",
                status_code=429,
                detail=detail,
                retryable=True,
                upstream_status=status,
                suggested_action="检查账户额度，或稍后重试",
                **common,
            )
        if status in (408, 504):
            return AppError(
                code="upstream_timeout",
                message="上游服务响应超时",
                status_code=504,
                detail=detail,
                retryable=True,
                upstream_status=status,
                suggested_action="稍后重试，并检查网络或上游服务状态",
                **common,
            )
        return AppError(
            code="upstream_request_failed",
            message="上游服务请求失败",
            status_code=502,
            detail=detail,
            retryable=status >= 500,
            upstream_status=status,
            suggested_action="检查 API 配置和上游服务状态",
            **common,
        )
    if isinstance(exc, httpx.TimeoutException):
        return AppError(
            code="upstream_timeout",
            message="连接上游服务超时",
            status_code=504,
            detail=redact_sensitive_text(exc),
            retryable=True,
            suggested_action="稍后重试，并检查网络或上游服务状态",
            **common,
        )
    if isinstance(exc, httpx.RequestError):
        return AppError(
            code="upstream_unreachable",
            message="无法连接上游服务",
            status_code=502,
            detail=redact_sensitive_text(exc),
            retryable=True,
            suggested_action="检查 API 地址、网络连接和代理设置",
            **common,
        )
    if isinstance(exc, (json.JSONDecodeError, httpx.DecodingError)):
        return AppError(
            code="provider_response_invalid",
            message="上游服务返回了无法解析的响应",
            status_code=502,
            detail=redact_sensitive_text(exc),
            retryable=False,
            suggested_action="检查 API 协议与预设是否匹配",
            **common,
        )
    return AppError(
        code=default_code,
        message=default_message,
        status_code=default_status_code,
        detail=redact_sensitive_text(exc),
        retryable=False,
        **common,
    )


def app_error_response(error: AppError, request_id: str | None = None) -> JSONResponse:
    resolved_request_id = request_id or error.request_id or get_request_id() or new_request_id()
    headers = {REQUEST_ID_HEADER: resolved_request_id}
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_dict(resolved_request_id),
        headers=headers,
    )


def _http_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "request_validation_failed",
        429: "rate_limited",
    }.get(status_code, "http_error")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = _request_id_from_request(request)
        logger.warning(
            "request failed requestId=%s code=%s source=%s",
            request_id,
            exc.code,
            exc.source,
        )
        return app_error_response(exc, request_id)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details: list[str] = []
        for item in exc.errors()[:10]:
            location = ".".join(str(part) for part in item.get("loc", ()))
            details.append(f"{location}: {item.get('msg', 'invalid value')} ({item.get('type', 'validation_error')})")
        error = AppError(
            code="request_validation_failed",
            message="请求参数无效",
            detail="; ".join(details) or None,
            source="request.validation",
            status_code=422,
            suggested_action="检查输入内容后重试",
        )
        return app_error_response(error, _request_id_from_request(request))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        code = _http_error_code(exc.status_code)
        message = "请求失败"
        detail_text: str | None = None
        suggested_action: str | None = None
        if isinstance(detail, dict):
            code = str(detail.get("code") or code)
            message = str(detail.get("message") or message)
            raw_detail = detail.get("detail")
            if raw_detail is not None:
                detail_text = raw_detail if isinstance(raw_detail, str) else json.dumps(raw_detail, ensure_ascii=False)
            suggested_action = detail.get("suggestedAction")
        elif isinstance(detail, str):
            message = detail
        elif detail is not None:
            detail_text = redact_sensitive_text(detail)
        error = AppError(
            code=code,
            message=message,
            detail=detail_text,
            source="http",
            status_code=exc.status_code,
            suggested_action=suggested_action,
        )
        return app_error_response(error, _request_id_from_request(request))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id_from_request(request)
        logger.exception("unhandled request error requestId=%s", request_id)
        error = AppError(
            code="internal_error",
            message="服务器内部错误",
            source="server",
            status_code=500,
            suggested_action="重试操作；若问题持续，请复制 requestId 以便定位",
        )
        return app_error_response(error, request_id)
