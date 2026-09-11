"""GitHub Copilot device-code OAuth (T-830).

Client id / endpoints align with pi ``packages/ai/src/auth/oauth/github-copilot.ts``.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from app.llm.oauth.http import request_json

# VS Code Copilot Chat 公开 client id（与 pi / GitHub Copilot CLI 相同）
CLIENT_ID = "Iv1.b507a08c87ecfe98"
GITHUB_UA = "GitHubCopilotChat/0.35.0"
COPILOT_HEADERS = {
    "User-Agent": GITHUB_UA,
    "Editor-Version": "vscode/1.107.0",
    "Editor-Plugin-Version": "copilot-chat/0.35.0",
    "Copilot-Integration-Id": "vscode-chat",
    "X-GitHub-Api-Version": "2026-06-01",
}
DEFAULT_DOMAIN = "github.com"
DEFAULT_API_BASE = "https://api.individual.githubcopilot.com"


def extra_request_headers() -> dict[str, str]:
    return dict(COPILOT_HEADERS)


def normalize_domain(raw: str | None) -> str | None:
    trimmed = (raw or "").strip()
    if not trimmed:
        return None
    try:
        url = trimmed if "://" in trimmed else f"https://{trimmed}"
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:  # noqa: BLE001
        return None
    return host or None


def _urls(domain: str) -> dict[str, str]:
    host = domain or DEFAULT_DOMAIN
    return {
        "deviceCodeUrl": f"https://{host}/login/device/code",
        "accessTokenUrl": f"https://{host}/login/oauth/access_token",
        "copilotTokenUrl": f"https://api.{host}/copilot_internal/v2/token",
    }


def api_base_from_token(token: str, *, enterprise_domain: str | None = None) -> str:
    match = None
    for part in (token or "").split(";"):
        piece = part.strip()
        if piece.startswith("proxy-ep="):
            match = piece.split("=", 1)[1].strip()
            break
    if match:
        api_host = match
        if match.startswith("proxy."):
            api_host = "api." + match[len("proxy.") :]
        return f"https://{api_host}"
    if enterprise_domain:
        return f"https://copilot-api.{enterprise_domain}"
    return DEFAULT_API_BASE


def _trust_verification_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Untrusted verification_uri")
    return parsed.geturl()


async def start_device_flow(domain: str = DEFAULT_DOMAIN) -> dict[str, Any]:
    urls = _urls(domain)
    status, data, text = await request_json(
        "POST",
        urls["deviceCodeUrl"],
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": GITHUB_UA,
        },
        data={"client_id": CLIENT_ID, "scope": "read:user"},
    )
    if status >= 400 or not isinstance(data, dict):
        raise RuntimeError(f"GitHub device code 失败 ({status}): {text[:300]}")
    device_code = data.get("device_code")
    user_code = data.get("user_code")
    verification_uri = data.get("verification_uri")
    interval = data.get("interval")
    expires_in = data.get("expires_in")
    if not isinstance(device_code, str) or not isinstance(user_code, str) or not isinstance(verification_uri, str):
        raise RuntimeError("GitHub device code 响应字段无效")
    if not isinstance(expires_in, (int, float)):
        raise RuntimeError("GitHub device code 缺少 expires_in")
    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": _trust_verification_uri(str(verification_uri)),
        "interval": int(interval) if isinstance(interval, (int, float)) else 5,
        "expires_in": int(expires_in),
    }


async def poll_github_access_token(domain: str, device_code: str) -> dict[str, Any]:
    urls = _urls(domain)
    status, data, text = await request_json(
        "POST",
        urls["accessTokenUrl"],
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": GITHUB_UA,
        },
        data={
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )
    if not isinstance(data, dict):
        return {"status": "failed", "message": f"GitHub token 响应无效 ({status}): {text[:200]}"}
    token = data.get("access_token")
    if isinstance(token, str) and token.strip():
        return {"status": "complete", "access_token": token.strip()}
    error = str(data.get("error") or "")
    if error == "authorization_pending":
        return {"status": "pending"}
    if error == "slow_down":
        interval = data.get("interval")
        return {
            "status": "slow_down",
            "intervalSeconds": int(interval) if isinstance(interval, (int, float)) else None,
        }
    if error == "expired_token":
        return {"status": "expired", "message": "设备码已过期，请重新登录"}
    desc = data.get("error_description")
    suffix = f": {desc}" if desc else ""
    return {"status": "failed", "message": f"Device flow failed: {error}{suffix}"}


async def exchange_copilot_token(
    github_access_token: str,
    *,
    enterprise_domain: str | None = None,
) -> dict[str, Any]:
    domain = enterprise_domain or DEFAULT_DOMAIN
    urls = _urls(domain)
    status, data, text = await request_json(
        "GET",
        urls["copilotTokenUrl"],
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {github_access_token}",
            **COPILOT_HEADERS,
        },
    )
    if status >= 400 or not isinstance(data, dict):
        raise RuntimeError(f"换发 Copilot token 失败 ({status}): {text[:300]}")
    token = data.get("token")
    expires_at = data.get("expires_at")
    if not isinstance(token, str) or not isinstance(expires_at, (int, float)):
        raise RuntimeError("Copilot token 响应字段无效")
    expires_ms = int(expires_at) * 1000 - 5 * 60 * 1000
    return {
        "provider": "github-copilot",
        "accessToken": token,
        "refreshToken": github_access_token,
        "expiresAt": expires_ms,
        "accountId": None,
        "enterpriseUrl": enterprise_domain,
    }


def record_to_apply(record: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
    access = str(record.get("accessToken") or "")
    base = api_base_from_token(access, enterprise_domain=record.get("enterpriseUrl") or None)
    return base, access, extra_request_headers()


async def refresh_record(record: dict[str, Any]) -> dict[str, Any]:
    refresh = str(record.get("refreshToken") or "").strip()
    if not refresh:
        raise RuntimeError("缺少 GitHub refresh token，请重新登录 Copilot")
    enterprise = record.get("enterpriseUrl") or None
    if isinstance(enterprise, str):
        enterprise = normalize_domain(enterprise)
    return await exchange_copilot_token(refresh, enterprise_domain=enterprise)


def still_fresh(record: dict[str, Any], *, now_ms: int | None = None) -> bool:
    from app.llm.oauth.store import needs_refresh

    return not needs_refresh(record, now_ms=now_ms if now_ms is not None else int(time.time() * 1000))
