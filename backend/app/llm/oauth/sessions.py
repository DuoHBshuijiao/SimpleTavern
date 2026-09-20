"""In-memory OAuth login sessions (T-830). Device codes are never written to disk."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, "OAuthSession"] = {}


@dataclass
class OAuthSession:
    id: str
    preset_id: str
    provider: str
    method: str
    created_at: float
    expires_at: float
    interval: float = 5.0
    device_code: str | None = None
    user_code: str | None = None
    verification_uri: str | None = None
    enterprise_domain: str | None = None
    device_auth_id: str | None = None
    code_verifier: str | None = None
    state: str | None = None
    authorize_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def create_session(**kwargs: Any) -> OAuthSession:
    sid = secrets.token_urlsafe(18)
    now = time.time()
    expires_in = float(kwargs.pop("expires_in", 900) or 900)
    session = OAuthSession(id=sid, created_at=now, expires_at=now + expires_in, **kwargs)
    with _lock:
        _sessions[sid] = session
        _gc_locked(now)
    return session


def get_session(session_id: str) -> OAuthSession | None:
    sid = (session_id or "").strip()
    if not sid:
        return None
    with _lock:
        _gc_locked(time.time())
        session = _sessions.get(sid)
        if session is None:
            return None
        if session.expires_at <= time.time():
            _sessions.pop(sid, None)
            return None
        return session


def drop_session(session_id: str) -> None:
    with _lock:
        _sessions.pop((session_id or "").strip(), None)


def _gc_locked(now: float) -> None:
    dead = [k for k, s in _sessions.items() if s.expires_at <= now]
    for key in dead:
        _sessions.pop(key, None)
