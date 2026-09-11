"""OAuth token persistence (T-830). Tokens live beside data/, not in settings.json."""

from __future__ import annotations

from typing import Any

from app import storage as storage_mod
from app.storage import read_json, write_json

_REFRESH_SKEW_MS = 5 * 60 * 1000


def _path():
    return storage_mod._data_dir() / "oauth_tokens.json"


def load_all() -> dict[str, dict[str, Any]]:
    try:
        raw = read_json(_path())
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        return {}
    presets = raw.get("presets")
    if not isinstance(presets, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in presets.items():
        pid = str(key).strip()
        if pid and isinstance(value, dict):
            out[pid] = dict(value)
    return out


def load_token(preset_id: str) -> dict[str, Any] | None:
    pid = (preset_id or "").strip()
    if not pid:
        return None
    rec = load_all().get(pid)
    return dict(rec) if rec else None


def save_token(preset_id: str, record: dict[str, Any]) -> None:
    pid = (preset_id or "").strip()
    if not pid:
        raise ValueError("preset_id required")
    all_tokens = load_all()
    all_tokens[pid] = {
        "provider": str(record.get("provider") or "").strip(),
        "accessToken": str(record.get("accessToken") or ""),
        "refreshToken": str(record.get("refreshToken") or ""),
        "expiresAt": record.get("expiresAt"),
        "accountId": record.get("accountId") or None,
        "enterpriseUrl": record.get("enterpriseUrl") or None,
    }
    write_json(_path(), {"presets": all_tokens})


def delete_token(preset_id: str) -> None:
    pid = (preset_id or "").strip()
    if not pid:
        return
    all_tokens = load_all()
    if pid not in all_tokens:
        return
    del all_tokens[pid]
    write_json(_path(), {"presets": all_tokens})


def prune_oauth_tokens(keep_preset_ids: set[str]) -> None:
    keep = {str(x).strip() for x in keep_preset_ids if str(x).strip()}
    all_tokens = load_all()
    trimmed = {k: v for k, v in all_tokens.items() if k in keep}
    if trimmed != all_tokens:
        write_json(_path(), {"presets": trimmed})


def public_status(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {"loggedIn": False, "expiresAt": None, "accountId": None, "provider": None}
    access = str(record.get("accessToken") or "").strip()
    refresh = str(record.get("refreshToken") or "").strip()
    return {
        "loggedIn": bool(access or refresh),
        "expiresAt": record.get("expiresAt"),
        "accountId": record.get("accountId") or None,
        "provider": record.get("provider") or None,
        "enterpriseUrl": record.get("enterpriseUrl") or None,
    }


def needs_refresh(record: dict[str, Any], *, now_ms: int) -> bool:
    expires = record.get("expiresAt")
    if not isinstance(expires, (int, float)):
        return True
    return now_ms >= int(expires) - _REFRESH_SKEW_MS
