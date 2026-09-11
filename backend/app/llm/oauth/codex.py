"""OpenAI Codex (ChatGPT) OAuth (T-830).

Device-code is the default for SimpleTavern's local web UI.
PKCE is paste-callback only (no localhost:1455 server).
Constants align with pi ``packages/ai/src/auth/oauth/openai-codex.ts``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from app.llm.oauth.http import request_json

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTH_BASE_URL = "https://auth.openai.com"
AUTHORIZE_URL = f"{AUTH_BASE_URL}/oauth/authorize"
TOKEN_URL = f"{AUTH_BASE_URL}/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
DEVICE_USER_CODE_URL = f"{AUTH_BASE_URL}/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = f"{AUTH_BASE_URL}/api/accounts/deviceauth/token"
DEVICE_VERIFICATION_URI = f"{AUTH_BASE_URL}/codex/device"
DEVICE_REDIRECT_URI = f"{AUTH_BASE_URL}/deviceauth/callback"
DEVICE_CODE_TIMEOUT_SECONDS = 15 * 60
SCOPE = "openid profile email offline_access"
JWT_CLAIM_PATH = "https://api.openai.com/auth"
ORIGINATOR = "simpletavern"


def extra_request_headers(account_id: str | None) -> dict[str, str]:
    headers = {
        "originator": ORIGINATOR,
        "OpenAI-Beta": "responses=experimental",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id
    return headers


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def create_authorization_flow() -> dict[str, str]:
    verifier, challenge = generate_pkce()
    state = secrets.token_hex(16)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": ORIGINATOR,
        }
    )
    return {
        "verifier": verifier,
        "state": state,
        "authorizeUrl": f"{AUTHORIZE_URL}?{query}",
    }


def parse_authorization_input(raw: str) -> dict[str, str | None]:
    value = (raw or "").strip()
    if not value:
        return {}
    try:
        url = urlparse(value)
        if url.scheme and url.netloc:
            qs = parse_qs(url.query)
            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            return {"code": code, "state": state}
    except Exception:  # noqa: BLE001
        pass
    if "#" in value:
        code, state = value.split("#", 1)
        return {"code": code or None, "state": state or None}
    if "code=" in value:
        qs = parse_qs(value)
        return {"code": (qs.get("code") or [None])[0], "state": (qs.get("state") or [None])[0]}
    return {"code": value, "state": None}


def decode_account_id(access_token: str) -> str | None:
    try:
        parts = access_token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
        auth = payload.get(JWT_CLAIM_PATH) if isinstance(payload, dict) else None
        account_id = auth.get("chatgpt_account_id") if isinstance(auth, dict) else None
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def _token_record(access: str, refresh: str, expires_in: int) -> dict[str, Any]:
    account_id = decode_account_id(access)
    if not account_id:
        raise RuntimeError("无法从 Codex token 解析 chatgpt_account_id")
    return {
        "provider": "openai-codex",
        "accessToken": access,
        "refreshToken": refresh,
        "expiresAt": int(time.time() * 1000) + int(expires_in) * 1000,
        "accountId": account_id,
        "enterpriseUrl": None,
    }


async def _read_token_response(status: int, data: Any, text: str, operation: str) -> dict[str, Any]:
    if status >= 400 or not isinstance(data, dict):
        raise RuntimeError(f"OpenAI Codex token {operation} 失败 ({status}): {text[:300]}")
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = data.get("expires_in")
    if not isinstance(access, str) or not isinstance(refresh, str) or not isinstance(expires_in, (int, float)):
        raise RuntimeError(f"OpenAI Codex token {operation} 响应缺字段")
    return _token_record(access, refresh, int(expires_in))


async def exchange_authorization_code(code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
    status, data, text = await request_json(
        "POST",
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
    )
    return await _read_token_response(status, data, text, "exchange")


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    status, data, text = await request_json(
        "POST",
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
    )
    return await _read_token_response(status, data, text, "refresh")


async def start_device_auth() -> dict[str, Any]:
    status, data, text = await request_json(
        "POST",
        DEVICE_USER_CODE_URL,
        headers={"Content-Type": "application/json"},
        json_body={"client_id": CLIENT_ID},
    )
    if status == 404:
        raise RuntimeError("OpenAI Codex 设备码登录未对该账号启用，请改用浏览器粘贴回调。")
    if status >= 400 or not isinstance(data, dict):
        raise RuntimeError(f"Codex 设备码请求失败 ({status}): {text[:300]}")
    device_auth_id = data.get("device_auth_id")
    user_code = data.get("user_code")
    interval = data.get("interval")
    if isinstance(interval, str):
        try:
            interval = float(interval.strip())
        except ValueError:
            interval = None
    if not isinstance(device_auth_id, str) or not isinstance(user_code, str) or not isinstance(interval, (int, float)):
        raise RuntimeError("Codex 设备码响应字段无效")
    return {
        "device_auth_id": device_auth_id,
        "user_code": user_code,
        "interval": max(1, int(interval)),
        "expires_in": DEVICE_CODE_TIMEOUT_SECONDS,
        "verification_uri": DEVICE_VERIFICATION_URI,
    }


async def poll_device_auth(device_auth_id: str, user_code: str) -> dict[str, Any]:
    status, data, text = await request_json(
        "POST",
        DEVICE_TOKEN_URL,
        headers={"Content-Type": "application/json"},
        json_body={"device_auth_id": device_auth_id, "user_code": user_code},
    )
    if status in {403, 404}:
        return {"status": "pending"}
    if status < 400 and isinstance(data, dict):
        code = data.get("authorization_code")
        verifier = data.get("code_verifier")
        if isinstance(code, str) and isinstance(verifier, str):
            return {"status": "complete", "authorization_code": code, "code_verifier": verifier}
        return {"status": "failed", "message": "Codex device auth 响应缺字段"}
    error_code = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, str):
            error_code = err
        elif isinstance(err, dict):
            error_code = err.get("code")
    if error_code == "deviceauth_authorization_pending":
        return {"status": "pending"}
    if error_code == "slow_down":
        return {"status": "slow_down"}
    return {"status": "failed", "message": f"Codex device auth 失败 ({status}): {text[:200]}"}


def record_to_apply(record: dict[str, Any]) -> tuple[str | None, str, dict[str, str]]:
    access = str(record.get("accessToken") or "")
    account_id = record.get("accountId") or decode_account_id(access)
    return None, access, extra_request_headers(str(account_id) if account_id else None)


async def refresh_record(record: dict[str, Any]) -> dict[str, Any]:
    refresh = str(record.get("refreshToken") or "").strip()
    if not refresh:
        raise RuntimeError("缺少 Codex refresh token，请重新登录")
    return await refresh_access_token(refresh)
