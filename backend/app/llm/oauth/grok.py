"""xAI device grant compatibility with the public Grok client; optional configured client ID."""
from __future__ import annotations

import time
from urllib.parse import urlsplit
from app.llm.oauth.http import request_json

ISSUER = "https://auth.x.ai"
DEFAULT_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPES = "openid profile email offline_access grok-cli:access api:access"


async def discovery() -> dict:
    status, data, _ = await request_json("GET", ISSUER + "/.well-known/openid-configuration")
    if status != 200 or not isinstance(data, dict) or data.get("issuer") != ISSUER:
        raise ValueError("无法获取 xAI OAuth 配置")
    for key in ("device_authorization_endpoint", "token_endpoint", "userinfo_endpoint", "revocation_endpoint"):
        value = str(data.get(key) or "")
        if not value.startswith("https://") or urlsplit(value).netloc != "auth.x.ai":
            raise ValueError("xAI OAuth 端点不在官方域名")
    return data


async def start_device_flow(client_id: str) -> dict:
    if not client_id:
        raise ValueError("请配置此应用注册的 xAI OAuth client ID")
    config = await discovery()
    status, data, _ = await request_json("POST", config["device_authorization_endpoint"],
        data={"client_id": client_id, "scope": SCOPES}, headers={"Accept": "application/json"})
    if status != 200 or not isinstance(data, dict) or not all(data.get(k) for k in ("device_code", "user_code", "verification_uri")):
        raise ValueError("xAI 设备授权启动失败，请检查 client ID 与账号权限")
    uri = str(data["verification_uri"])
    if urlsplit(uri).scheme != "https" or urlsplit(uri).hostname not in {"auth.x.ai", "accounts.x.ai", "x.ai", "grok.com"}:
        raise ValueError("xAI 验证链接域名无效")
    return {**data, "expires_in": min(1800, max(1, int(data.get("expires_in", 900)))),
            "interval": max(5, int(data.get("interval", 5)))}


async def _record(data: dict, client_id: str, prior: dict | None = None) -> dict:
    prior = prior or {}
    if not data.get("access_token") or str(data.get("token_type", "Bearer")).lower() != "bearer":
        raise ValueError("xAI 未返回 Bearer 令牌")
    config = await discovery()
    status, identity, _ = await request_json("GET", config["userinfo_endpoint"],
        headers={"Authorization": "Bearer " + data["access_token"], "Accept": "application/json"})
    if status != 200 or not isinstance(identity, dict) or not identity.get("sub"):
        raise ValueError("无法确认 xAI 登录账号")
    if prior.get("subject") and prior["subject"] != identity["sub"]:
        raise ValueError("xAI 刷新账号不一致")
    scopes = str(data.get("scope") or " ".join(prior.get("scopes") or []) or SCOPES).split()
    if "api:access" not in scopes:
        raise ValueError("xAI 尚未授权 API 访问")
    return {**prior, "provider": "xai-oauth", "clientId": client_id, "issuer": ISSUER,
        "subject": identity["sub"], "accountId": identity["sub"], "email": identity.get("email"),
        "accessToken": data["access_token"], "refreshToken": data.get("refresh_token") or prior.get("refreshToken"),
        "expiresAt": int(time.time() * 1000) + int(data.get("expires_in", 3600)) * 1000, "scopes": scopes}


async def poll_device_flow(client_id: str, device_code: str) -> dict:
    config = await discovery()
    status, data, _ = await request_json("POST", config["token_endpoint"], data={"client_id": client_id,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": device_code})
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        return {"status": "complete", "record": await _record(data, client_id)}
    error = str(data.get("error") or "") if isinstance(data, dict) else ""
    state = {"authorization_pending": "pending", "slow_down": "slow_down", "expired_token": "expired",
             "access_denied": "failed"}.get(error, "failed")
    return {"status": state, "message": "xAI 授权尚未完成" if state == "pending" else "xAI 授权失败或已过期"}


async def refresh_record(record: dict) -> dict:
    config = await discovery()
    status, data, _ = await request_json("POST", config["token_endpoint"], data={"grant_type": "refresh_token",
        "client_id": record["clientId"], "refresh_token": record["refreshToken"]})
    if status != 200 or not isinstance(data, dict):
        raise ValueError("xAI 刷新失败，请重新登录")
    return await _record(data, record["clientId"], record)


async def revoke(record: dict) -> bool:
    try:
        config = await discovery()
        status, _, _ = await request_json("POST", config["revocation_endpoint"], data={
            "client_id": record["clientId"], "token": record.get("refreshToken") or record.get("accessToken") or "",
            "token_type_hint": "refresh_token" if record.get("refreshToken") else "access_token"})
        return status == 200
    except Exception:
        return False
