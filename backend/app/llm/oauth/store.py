"""OAuth token persistence (T-830). Tokens live beside data/, not in settings.json."""

from __future__ import annotations

from typing import Any
import base64
import os
import threading

from app import storage as storage_mod
from app.storage import read_json, write_json

_REFRESH_SKEW_MS = 5 * 60 * 1000
_store_lock = threading.RLock()


def _crypt(value: bytes, *, decrypt: bool = False) -> bytes:
    """Windows DPAPI binds credentials to the current OS user, without extra packages."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    operation = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("无法读取或保护当前系统账号的 OAuth 凭据")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def _write_tokens(tokens: dict) -> None:
    import json
    value = {"presets": tokens}
    if os.name == "nt":
        value = {"protection": "windows-dpapi", "payload": base64.b64encode(_crypt(json.dumps(value).encode())).decode()}
    write_json(_path(), value)
    if os.name != "nt":
        os.chmod(_path(), 0o600)


def _path():
    return storage_mod._data_dir() / "oauth_tokens.json"


def load_all() -> dict[str, dict[str, Any]]:
    try:
        raw = read_json(_path())
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("protection") == "windows-dpapi":
        import json
        raw = json.loads(_crypt(base64.b64decode(raw["payload"]), decrypt=True))
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
    with _store_lock:
        all_tokens = load_all()
        allowed = {"provider", "accessToken", "refreshToken", "expiresAt", "accountId", "enterpriseUrl",
                   "clientId", "hostId", "subject", "email", "issuer", "idToken", "scopes", "plan"}
        all_tokens[pid] = {key: val for key, val in record.items() if key in allowed}
        _write_tokens(all_tokens)


def delete_token(preset_id: str) -> None:
    pid = (preset_id or "").strip()
    if not pid:
        return
    with _store_lock:
        all_tokens = load_all()
        if pid not in all_tokens:
            return
        del all_tokens[pid]
        _write_tokens(all_tokens)


def replace_token_if_current(preset_id: str, expected: dict, replacement: dict) -> bool:
    with _store_lock:
        if load_token(preset_id) != expected:
            return False
        save_token(preset_id, replacement)
        return True


def prune_oauth_tokens(keep_preset_ids: set[str]) -> None:
    keep = {str(x).strip() for x in keep_preset_ids if str(x).strip()}
    with _store_lock:
        all_tokens = load_all()
        trimmed = {k: v for k, v in all_tokens.items() if k in keep}
        from app.llm.oauth.sessions import cancel_preset_sessions
        for preset_id in all_tokens.keys() - keep:
            cancel_preset_sessions(preset_id)
        if trimmed != all_tokens:
            _write_tokens(trimmed)


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
        "email": record.get("email") or None,
        "subscriptionAuthorized": "chatgpt.tokens.use.direct" in (record.get("scopes") or []),
    }


def needs_refresh(record: dict[str, Any], *, now_ms: int) -> bool:
    expires = record.get("expiresAt")
    if not isinstance(expires, (int, float)):
        return True
    return now_ms >= int(expires) - _REFRESH_SKEW_MS
