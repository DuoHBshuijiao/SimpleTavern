"""Vertex 服务账号鉴权（T-832）。

预设 ``apiKey`` 存服务账号 JSON。这里用其中的私钥签 RS256 JWT，向 JSON 里的 ``token_uri`` 换 access token，
在内存里缓存，临近过期时刷新。依据 https://developers.google.com/identity/protocols/oauth2/service-account 。

私钥和 token 只留在本模块：错误详情不带原文，HTTP 日志不记请求体和响应体。
读设置和备份时用 ``redact_settings`` 隐去 ``private_key``，写设置时用 ``restore_settings`` 还原。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.errors import AppError, as_app_error
from app.llm.types import ANTHROPIC_MESSAGES_PROTOCOL, is_vertex_service_account_style

_SOURCE = "llm.vertex_auth"
_PROVIDER = "anthropic"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_JWT_LIFETIME_SECONDS = 3600
_REFRESH_MARGIN_SECONDS = 300
_DEFAULT_EXPIRES_IN = 3600
_MAX_ERROR_DETAIL_CHARS = 500

# 读设置 / 备份时替换 private_key 的占位值；不含任何密钥信息。
REDACTED_PRIVATE_KEY = "__simpletavern_private_key_hidden__"

# 令牌交换阶段的所有错误都以这句开头，用户才分得清是换 token 失败还是 Vertex 本身连不上
_TOKEN_STAGE = "获取 Vertex 访问令牌失败"

_PEM_RE = re.compile(r"-----BEGIN[^-]*-----.*?(-----END[^-]*-----|$)", re.DOTALL)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*")
_GOOGLE_TOKEN_RE = re.compile(r"\bya29\.[A-Za-z0-9._-]+")


def looks_like_service_account_json(value: Any) -> bool:
    """快速判断文本像不像服务账号 JSON，用来挡住把它当普通 API Key 发出去的错配。"""
    text = str(value or "").strip()
    return text.startswith("{") and ('"private_key"' in text or '"service_account"' in text)


def scrub_secrets(text: Any) -> str:
    """从上游错误文本里去掉 PEM、JWT 和 Google access token。"""
    out = _PEM_RE.sub("***", str(text or ""))
    out = _JWT_RE.sub("***", out)
    return _GOOGLE_TOKEN_RE.sub("***", out)


def _config_error(detail: str) -> AppError:
    return AppError(
        code="config_invalid",
        message=f"{_TOKEN_STAGE}：服务账号 JSON 无效",
        detail=detail,
        source=_SOURCE,
        status_code=400,
        provider=_PROVIDER,
        protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        suggested_action="在 Google Cloud 控制台下载服务账号密钥，把 JSON 全文粘贴到预设的密钥框",
    )


@dataclass(frozen=True)
class ServiceAccount:
    client_email: str
    private_key: str = field(repr=False)
    private_key_id: str
    token_uri: str


def parse_service_account(api_key: str) -> ServiceAccount:
    try:
        data = json.loads(api_key or "")
    except json.JSONDecodeError as exc:
        # exc.msg 只描述语法错误，不含原文
        raise _config_error(f"not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}") from None
    if not isinstance(data, dict):
        raise _config_error("expected a JSON object")
    if data.get("type") != "service_account":
        raise _config_error('field "type" must be "service_account"')
    missing = [k for k in ("client_email", "private_key", "token_uri") if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing:
        raise _config_error("missing fields: " + ", ".join(missing))
    if data["private_key"] == REDACTED_PRIVATE_KEY:
        raise _config_error("private_key was hidden in this copy of the settings; paste the service account JSON again")
    token_uri = data["token_uri"].strip()
    if not token_uri.startswith(("http://", "https://")):
        raise _config_error("token_uri must be an http(s) URL")
    private_key_id = data.get("private_key_id")
    return ServiceAccount(
        client_email=data["client_email"].strip(),
        private_key=data["private_key"],
        private_key_id=private_key_id.strip() if isinstance(private_key_id, str) else "",
        token_uri=token_uri,
    )


def _sign_assertion(account: ServiceAccount, *, now: int) -> str:
    import jwt

    claims = {
        "iss": account.client_email,
        "scope": _SCOPE,
        "aud": account.token_uri,
        "iat": now,
        "exp": now + _JWT_LIFETIME_SECONDS,
    }
    headers = {"kid": account.private_key_id} if account.private_key_id else None
    try:
        return jwt.encode(claims, account.private_key, algorithm="RS256", headers=headers)
    except Exception:  # noqa: BLE001 - 不把底层异常文本带进错误详情
        raise _config_error("private_key cannot be used for RS256 signing") from None


def _token_error(response: httpx.Response) -> AppError:
    status = response.status_code
    detail = f"HTTP {status}"
    try:
        body = response.json()
    except (TypeError, ValueError):
        body = None
    if isinstance(body, dict):
        parts = [str(body[k]) for k in ("error", "error_description") if body.get(k)]
        if parts:
            detail = f"{detail}: " + ": ".join(parts)
    detail = scrub_secrets(detail)[:_MAX_ERROR_DETAIL_CHARS]
    common: dict[str, Any] = {
        "source": _SOURCE,
        "provider": _PROVIDER,
        "protocol": ANTHROPIC_MESSAGES_PROTOCOL,
        "upstream_status": status,
        "detail": detail,
    }
    if status == 429:
        return AppError(
            code="provider_quota_exceeded",
            message=f"{_TOKEN_STAGE}：令牌服务限流（HTTP 429）",
            status_code=429,
            retryable=True,
            suggested_action="稍后重试",
            **common,
        )
    if status >= 500:
        return AppError(
            code="upstream_request_failed",
            message=f"{_TOKEN_STAGE}：令牌服务暂时不可用（HTTP {status}）",
            status_code=502,
            retryable=True,
            suggested_action="稍后重试，并检查网络或上游服务状态",
            **common,
        )
    return AppError(
        code="provider_auth_failed",
        message=f"{_TOKEN_STAGE}：令牌服务拒绝了服务账号（HTTP {status}）",
        status_code=403 if status == 403 else 401,
        suggested_action="检查服务账号密钥是否被停用或删除、本机时间是否准确，以及账号是否有 Vertex AI 权限",
        **common,
    )


async def _exchange_token(account: ServiceAccount) -> tuple[str, float]:
    from app.services.http_client import get_async_http_client
    from app.services.http_log import log_outbound

    now = int(time.time())
    form = {"grant_type": _GRANT_TYPE, "assertion": _sign_assertion(account, now=now)}
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    try:
        # 只记状态码：assertion 和 access_token 都不进 HTTP 日志
        async with log_outbound(
            source="llm",
            method="POST",
            url=account.token_uri,
            request_headers=headers,
            streaming=False,
        ) as _log:
            client = get_async_http_client()
            response = await client.post(account.token_uri, data=form, headers=headers, timeout=30)
            _log.set_response(status=response.status_code, headers=dict(response.headers))
            if response.status_code >= 400:
                raise _token_error(response)
            try:
                body = response.json()
            except (TypeError, ValueError):
                body = None
    except AppError:
        raise
    except Exception as exc:
        # 连接失败、断连、超时：保留原始原因和错误码，消息里点明是换 token 阶段
        error = as_app_error(
            exc,
            source=_SOURCE,
            default_code="provider_request_failed",
            default_message="请求令牌服务失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        )
        reason = scrub_secrets(error.detail or error.message)[:_MAX_ERROR_DETAIL_CHARS]
        error.message = f"{_TOKEN_STAGE}：{error.message}"
        error.detail = f"token_uri request failed: {reason}"
        error.suggested_action = "检查网络能否访问服务账号 JSON 里的 token_uri，然后重试"
        raise error from None
    if not isinstance(body, dict):
        raise AppError(
            code="provider_response_invalid",
            message=f"{_TOKEN_STAGE}：令牌服务返回的不是 JSON",
            detail="token response is not a JSON object",
            source=_SOURCE,
            status_code=502,
            provider=_PROVIDER,
            protocol=ANTHROPIC_MESSAGES_PROTOCOL,
            suggested_action="检查服务账号 JSON 中的 token_uri",
        )
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise AppError(
            code="provider_response_invalid",
            message=f"{_TOKEN_STAGE}：令牌服务没有返回 access token",
            detail="token response has no access_token",
            source=_SOURCE,
            status_code=502,
            provider=_PROVIDER,
            protocol=ANTHROPIC_MESSAGES_PROTOCOL,
            suggested_action="检查服务账号 JSON 中的 token_uri",
        )
    expires_in = body.get("expires_in")
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or expires_in <= 0:
        expires_in = _DEFAULT_EXPIRES_IN
    return token.strip(), time.time() + float(expires_in)


# sha256(密钥文本) → (token, 过期时间戳)；进程内缓存，不落盘
_token_cache: dict[str, tuple[str, float]] = {}
_token_locks: dict[str, asyncio.Lock] = {}


def _cache_key(api_key: str) -> str:
    return hashlib.sha256((api_key or "").strip().encode("utf-8")).hexdigest()


def _fresh_token(key: str) -> str | None:
    cached = _token_cache.get(key)
    if cached is not None and cached[1] - time.time() > _REFRESH_MARGIN_SECONDS:
        return cached[0]
    return None


async def get_access_token(api_key: str) -> str:
    """取可用 access token：缓存未到刷新线时直接返回，否则重新换取。"""
    account = parse_service_account(api_key)
    key = _cache_key(api_key)
    token = _fresh_token(key)
    if token is not None:
        return token
    lock = _token_locks.setdefault(key, asyncio.Lock())
    async with lock:
        token = _fresh_token(key)
        if token is not None:
            return token
        token, expires_at = await _exchange_token(account)
        _token_cache[key] = (token, expires_at)
        return token


def clear_token_cache() -> None:
    _token_cache.clear()


def finish_upstream_error(error: AppError, api_key: str) -> AppError:
    """Vertex 返回错误时：401 让缓存失效，下一次请求重新换取；错误文本里不留 token。"""
    key = _cache_key(api_key)
    cached = _token_cache.get(key)
    if cached is not None:
        if error.detail:
            error.detail = error.detail.replace(cached[0], "***")
        if error.message:
            error.message = error.message.replace(cached[0], "***")
    if error.upstream_status == 401:
        _token_cache.pop(key, None)
    if error.detail:
        error.detail = scrub_secrets(error.detail)
    return error


# ---------------------------------------------------------------------------
# 设置读写：对前端和备份隐去 private_key
# ---------------------------------------------------------------------------


def _holds_service_account(connection: Any) -> bool:
    api_key = getattr(connection, "apiKey", "")
    if not api_key:
        return False
    return is_vertex_service_account_style(getattr(connection, "authStyle", None)) or looks_like_service_account_json(api_key)


def redact_service_account_key(api_key: str) -> str:
    """返回隐去私钥的文本：能解析就只替换 private_key，解析不了就整段替换。"""
    try:
        data = json.loads(api_key)
    except (TypeError, ValueError):
        return REDACTED_PRIVATE_KEY
    if not isinstance(data, dict):
        return REDACTED_PRIVATE_KEY
    if "private_key" in data:
        data["private_key"] = REDACTED_PRIVATE_KEY
    return json.dumps(data, ensure_ascii=False, indent=2)


def restore_service_account_key(incoming: str, stored: str) -> str:
    """前端把隐去私钥的文本写回时还原。账号对不上就原样保留，使用时再明确报错。"""
    if REDACTED_PRIVATE_KEY not in (incoming or ""):
        return incoming
    if incoming.strip() == REDACTED_PRIVATE_KEY:
        return stored or incoming
    try:
        new_data = json.loads(incoming)
        old_data = json.loads(stored)
    except (TypeError, ValueError):
        return incoming
    if not isinstance(new_data, dict) or not isinstance(old_data, dict):
        return incoming
    same_account = all(new_data.get(k) == old_data.get(k) for k in ("client_email", "private_key_id"))
    if not same_account or not isinstance(old_data.get("private_key"), str):
        return incoming
    new_data["private_key"] = old_data["private_key"]
    return json.dumps(new_data, ensure_ascii=False, indent=2)


def _connections(settings: Any) -> list[Any]:
    return [settings.llm, *(settings.apiPresets or [])]


def redact_settings(settings: Any) -> Any:
    """返回可以交给前端或写进备份的副本。"""
    if not any(_holds_service_account(c) for c in _connections(settings)):
        return settings
    copy = settings.model_copy(deep=True)
    for connection in _connections(copy):
        if _holds_service_account(connection):
            connection.apiKey = redact_service_account_key(connection.apiKey)
    return copy


def settings_need_restore(settings: Any) -> bool:
    return any(REDACTED_PRIVATE_KEY in (getattr(c, "apiKey", "") or "") for c in _connections(settings))


def restore_settings(incoming: Any, stored: Any) -> None:
    """就地还原 incoming 中被隐去的私钥。预设按 id 对应，全局连接对全局连接。"""
    incoming.llm.apiKey = restore_service_account_key(incoming.llm.apiKey, stored.llm.apiKey)
    stored_presets = {p.id: p for p in (stored.apiPresets or [])}
    for preset in incoming.apiPresets or []:
        previous = stored_presets.get(preset.id)
        if previous is not None:
            preset.apiKey = restore_service_account_key(preset.apiKey, previous.apiKey)
