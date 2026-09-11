"""LLM OAuth 登录（T-830）：GitHub Copilot 设备码 / OpenAI Codex 设备码 + PKCE 粘贴。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.errors import AppError
from app.llm.oauth import codex, copilot
from app.llm.oauth.sessions import create_session, drop_session, get_session
from app.llm.oauth.store import delete_token, load_all, load_token, public_status, save_token
from app.storage import load_settings

router = APIRouter(tags=["llm-oauth"])

ProviderId = Literal["github-copilot", "openai-codex"]
LoginMethod = Literal["device_code", "pkce"]


class OAuthStartRequest(BaseModel):
    presetId: str
    providerId: str | None = None
    method: LoginMethod | None = None
    enterpriseUrl: str | None = Field(default=None, description="GitHub Enterprise 域名，空则 github.com")


class OAuthSessionRequest(BaseModel):
    sessionId: str


class OAuthCompletePkceRequest(BaseModel):
    sessionId: str
    callback: str


class OAuthLogoutRequest(BaseModel):
    presetId: str


def _preset_or_404(preset_id: str):
    settings = load_settings()
    preset = next((p for p in (settings.apiPresets or []) if p.id == preset_id), None)
    if preset is None:
        raise AppError(
            code="PRESET_NOT_FOUND",
            message=f"找不到 API 预设：{preset_id}",
            source="llm.oauth",
            status_code=404,
            suggested_action="在设置里打开对应预设后再登录",
        )
    return preset


def _provider_of(preset, requested: str | None) -> str:
    pid = (requested or getattr(preset, "providerId", None) or "").strip().lower()
    style = str(getattr(preset, "authStyle", "") or "").lower()
    if pid in {"github-copilot", "copilot"} or "copilot" in pid:
        return "github-copilot"
    if pid in {"openai-codex", "codex"} or "codex" in pid:
        return "openai-codex"
    if style == "oauth_device":
        return "github-copilot"
    if style == "oauth_pkce":
        return "openai-codex"
    raise AppError(
        code="oauth_provider_unsupported",
        message="当前预设不是 Copilot / Codex OAuth 厂商",
        source="llm.oauth",
        status_code=400,
        suggested_action="在预设名称里选择 GitHub Copilot 或 OpenAI Codex",
    )


@router.get("/llm/oauth/status")
def oauth_status(presetId: str | None = None) -> dict[str, Any]:
    if presetId:
        return {"presetId": presetId, **public_status(load_token(presetId))}
    return {"presets": {pid: public_status(rec) for pid, rec in load_all().items()}}


@router.post("/llm/oauth/start")
async def oauth_start(req: OAuthStartRequest) -> dict[str, Any]:
    preset = _preset_or_404(req.presetId)
    provider = _provider_of(preset, req.providerId)
    method = req.method or "device_code"
    if provider == "github-copilot":
        domain = copilot.normalize_domain(req.enterpriseUrl) or copilot.DEFAULT_DOMAIN
        device = await copilot.start_device_flow(domain)
        session = create_session(
            preset_id=preset.id,
            provider=provider,
            method="device_code",
            expires_in=device["expires_in"],
            interval=float(device["interval"]),
            device_code=device["device_code"],
            user_code=device["user_code"],
            verification_uri=device["verification_uri"],
            enterprise_domain=None if domain == copilot.DEFAULT_DOMAIN else domain,
        )
        return {
            "sessionId": session.id,
            "method": "device_code",
            "provider": provider,
            "userCode": session.user_code,
            "verificationUri": session.verification_uri,
            "interval": session.interval,
            "expiresIn": int(device["expires_in"]),
        }
    if method == "pkce":
        flow = codex.create_authorization_flow()
        session = create_session(
            preset_id=preset.id,
            provider=provider,
            method="pkce",
            expires_in=15 * 60,
            interval=2,
            code_verifier=flow["verifier"],
            state=flow["state"],
            authorize_url=flow["authorizeUrl"],
        )
        return {
            "sessionId": session.id,
            "method": "pkce",
            "provider": provider,
            "authorizeUrl": session.authorize_url,
            "redirectUri": codex.REDIRECT_URI,
            "expiresIn": 15 * 60,
        }
    device = await codex.start_device_auth()
    session = create_session(
        preset_id=preset.id,
        provider=provider,
        method="device_code",
        expires_in=device["expires_in"],
        interval=float(device["interval"]),
        device_auth_id=device["device_auth_id"],
        user_code=device["user_code"],
        verification_uri=device["verification_uri"],
    )
    return {
        "sessionId": session.id,
        "method": "device_code",
        "provider": provider,
        "userCode": session.user_code,
        "verificationUri": session.verification_uri,
        "interval": session.interval,
        "expiresIn": int(device["expires_in"]),
    }


@router.post("/llm/oauth/poll")
async def oauth_poll(req: OAuthSessionRequest) -> dict[str, Any]:
    session = get_session(req.sessionId)
    if session is None:
        return {"status": "expired", "message": "登录会话已过期，请重新开始"}
    if session.method != "device_code":
        return {"status": "failed", "message": "当前会话需要粘贴回调 URL，而不是轮询"}
    try:
        if session.provider == "github-copilot":
            assert session.device_code
            result = await copilot.poll_github_access_token(
                session.enterprise_domain or copilot.DEFAULT_DOMAIN,
                session.device_code,
            )
            if result["status"] in {"pending", "slow_down"}:
                return {"status": result["status"], "intervalSeconds": result.get("intervalSeconds") or session.interval}
            if result["status"] != "complete":
                return {"status": result["status"], "message": result.get("message")}
            record = await copilot.exchange_copilot_token(
                result["access_token"],
                enterprise_domain=session.enterprise_domain,
            )
        else:
            assert session.device_auth_id and session.user_code
            result = await codex.poll_device_auth(session.device_auth_id, session.user_code)
            if result["status"] in {"pending", "slow_down"}:
                return {"status": result["status"]}
            if result["status"] != "complete":
                return {"status": result["status"], "message": result.get("message")}
            record = await codex.exchange_authorization_code(
                result["authorization_code"],
                result["code_verifier"],
                codex.DEVICE_REDIRECT_URI,
            )
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            code="oauth_login_failed",
            message=str(exc) or "OAuth 登录失败",
            source="llm.oauth",
            status_code=502,
            suggested_action="确认网络可访问 GitHub / OpenAI 后重试",
        ) from exc
    save_token(session.preset_id, record)
    drop_session(session.id)
    return {"status": "complete", "presetId": session.preset_id, **public_status(record)}


@router.post("/llm/oauth/complete-pkce")
async def oauth_complete_pkce(req: OAuthCompletePkceRequest) -> dict[str, Any]:
    session = get_session(req.sessionId)
    if session is None or session.method != "pkce" or not session.code_verifier:
        raise AppError(
            code="oauth_session_invalid",
            message="PKCE 登录会话无效或已过期",
            source="llm.oauth",
            status_code=400,
            suggested_action="重新点击登录并粘贴最新的回调地址",
        )
    parsed = codex.parse_authorization_input(req.callback)
    code = parsed.get("code")
    state = parsed.get("state")
    if state and session.state and state != session.state:
        raise AppError(
            code="oauth_state_mismatch",
            message="OAuth state 不匹配",
            source="llm.oauth",
            status_code=400,
            suggested_action="请粘贴完整回调 URL，不要只粘贴 code",
        )
    if not code:
        raise AppError(
            code="oauth_code_missing",
            message="回调里没有 authorization code",
            source="llm.oauth",
            status_code=400,
            suggested_action="浏览器跳转到 localhost:1455 后，把地址栏完整 URL 粘贴回来",
        )
    try:
        record = await codex.exchange_authorization_code(code, session.code_verifier, codex.REDIRECT_URI)
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            code="oauth_login_failed",
            message=str(exc) or "兑换 Codex token 失败",
            source="llm.oauth",
            status_code=502,
            suggested_action="重新登录并尽快粘贴回调 URL（code 只能用一次）",
        ) from exc
    save_token(session.preset_id, record)
    drop_session(session.id)
    return {"status": "complete", "presetId": session.preset_id, **public_status(record)}


@router.post("/llm/oauth/cancel")
def oauth_cancel(req: OAuthSessionRequest) -> dict[str, Any]:
    drop_session(req.sessionId)
    return {"ok": True}


@router.post("/llm/oauth/logout")
def oauth_logout(req: OAuthLogoutRequest) -> dict[str, Any]:
    delete_token(req.presetId)
    return {"ok": True, "presetId": req.presetId}
