"""Attach stored OAuth tokens onto LlmPresetCredentials (T-830)."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import replace
from typing import Any

from app.llm.oauth import codex, copilot
from app.llm.oauth.store import load_token, needs_refresh, save_token

_COPILOT_IDS = {"github-copilot", "copilot"}
_CODEX_IDS = {"openai-codex", "codex"}


def _provider_kind(creds: Any, record: dict[str, Any] | None) -> str:
    raw = (record or {}).get("provider") or getattr(creds, "provider_id", None) or ""
    key = str(raw).strip().lower()
    if key in _COPILOT_IDS or "copilot" in key:
        return "github-copilot"
    if key in _CODEX_IDS or "codex" in key:
        return "openai-codex"
    style = str(getattr(creds, "auth_style", "") or "").lower()
    if style == "oauth_device":
        return "github-copilot"
    if style == "oauth_pkce":
        return "openai-codex"
    return key or "unknown"


def _login_error(name: str):
    from app.llm.preset_resolve import LlmPresetResolveError

    label = "GitHub Copilot" if "copilot" in name else "OpenAI Codex" if "codex" in name else "OAuth 供应商"
    return LlmPresetResolveError(
        "MISSING_OAUTH_LOGIN",
        f"请先在 API 预设中登录{label}。",
        status_code=401,
    )


def apply_stored_oauth(creds: Any) -> Any:
    from app.llm.preset_resolve import LlmPresetResolveError

    style = str(getattr(creds, "auth_style", "") or "").lower()
    if not style.startswith("oauth"):
        return creds
    preset_id = getattr(creds, "preset_id", None)
    provider_id = getattr(creds, "provider_id", None) or ""
    if not preset_id:
        raise _login_error(str(provider_id))
    record = load_token(preset_id)
    kind = _provider_kind(creds, record)
    if not record or not str(record.get("refreshToken") or record.get("accessToken") or "").strip():
        if creds.api_key:
            headers = (
                copilot.extra_request_headers()
                if kind == "github-copilot"
                else codex.extra_request_headers(None)
            )
            return replace(creds, extra_headers=headers)
        raise _login_error(str(provider_id))
    import time

    now_ms = int(time.time() * 1000)
    if needs_refresh(record, now_ms=now_ms) or not str(record.get("accessToken") or "").strip():
        try:
            if kind == "github-copilot":
                record = _run(copilot.refresh_record(record))
            elif kind == "openai-codex":
                record = _run(codex.refresh_record(record))
            else:
                raise RuntimeError(f"未知 OAuth 供应商：{kind}")
        except LlmPresetResolveError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LlmPresetResolveError(
                "OAUTH_REFRESH_FAILED",
                f"OAuth token 刷新失败，请重新登录：{exc}",
                status_code=401,
            ) from exc
        save_token(preset_id, record)
    if kind == "github-copilot":
        base_url, access, headers = copilot.record_to_apply(record)
    elif kind == "openai-codex":
        _base, access, headers = codex.record_to_apply(record)
        base_url = creds.base_url
    else:
        raise _login_error(kind)
    if not access:
        raise _login_error(kind)
    return replace(creds, api_key=access, base_url=base_url or creds.base_url, extra_headers=headers)


def _run(awaitable):  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, awaitable).result()
