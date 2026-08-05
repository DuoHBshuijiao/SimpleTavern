"""
世界书激活索引（T-803-3D）。

只缓存 globalActive / sessionChatIds，供 generate 热路径按 ID 加载正文，
避免每次 `list_worldbooks()` 全库读盘 + validate。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_INDEX_VERSION = 1
_index_lock = threading.RLock()
_index_dirty = False
_memory_cache: dict[str, Any] | None = None
_memory_mtime_ns: int | None = None


def _index_path() -> Path:
    from app.storage import _data_dir

    return _data_dir() / "worldbook_index.json"


def _empty_index() -> dict[str, Any]:
    return {"version": _INDEX_VERSION, "rebuilt": False, "byId": {}}


def _normalize_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    global_active = bool(raw.get("globalActive", False))
    sessions_raw = raw.get("sessionChatIds") or []
    if not isinstance(sessions_raw, list):
        sessions_raw = []
    session_ids = [str(x).strip() for x in sessions_raw if str(x).strip()]
    return {"globalActive": global_active, "sessionChatIds": session_ids}


def _load_index_unlocked() -> dict[str, Any]:
    global _memory_cache, _memory_mtime_ns
    path = _index_path()
    if not path.is_file():
        _memory_cache = _empty_index()
        _memory_mtime_ns = None
        return dict(_memory_cache)

    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = None

    if (
        _memory_cache is not None
        and _memory_mtime_ns is not None
        and mtime_ns is not None
        and mtime_ns == _memory_mtime_ns
    ):
        return dict(_memory_cache)

    from app.storage import read_json

    try:
        raw = read_json(path)
    except Exception as exc:
        raise RuntimeError(f"worldbook_index_read_failed: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("worldbook_index_corrupt: root must be object")
    by_id_raw = raw.get("byId") or {}
    if not isinstance(by_id_raw, dict):
        raise RuntimeError("worldbook_index_corrupt: byId must be object")
    by_id: dict[str, dict[str, Any]] = {}
    for wid, entry in by_id_raw.items():
        bid = str(wid or "").strip()
        normalized = _normalize_entry(entry)
        if bid and normalized:
            by_id[bid] = normalized
    data = {
        "version": int(raw.get("version") or _INDEX_VERSION),
        "rebuilt": bool(raw.get("rebuilt")),
        "byId": by_id,
    }
    _memory_cache = data
    _memory_mtime_ns = mtime_ns
    return dict(data)


def _write_index_unlocked(data: dict[str, Any]) -> None:
    global _memory_cache, _memory_mtime_ns, _index_dirty
    from app.storage import write_json

    write_json(_index_path(), data)
    _memory_cache = dict(data)
    try:
        _memory_mtime_ns = _index_path().stat().st_mtime_ns
    except OSError:
        _memory_mtime_ns = None
    _index_dirty = False


def rebuild_worldbook_index() -> dict[str, Any]:
    """全库轻量重建：读每本世界书的激活字段，不保留 entries。"""
    from app.storage import _worldbooks_dir, list_json_files, read_json

    by_id: dict[str, dict[str, Any]] = {}
    base = _worldbooks_dir()
    if base.exists():
        for path in list_json_files(base):
            try:
                raw = read_json(path)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            wid = str(raw.get("id") or path.stem).strip()
            if not wid:
                continue
            normalized = _normalize_entry(raw)
            if normalized:
                by_id[wid] = normalized
    data = {"version": _INDEX_VERSION, "rebuilt": True, "byId": by_id}
    with _index_lock:
        _write_index_unlocked(data)
    return data


def warm_worldbook_index() -> dict[str, Any]:
    return rebuild_worldbook_index()


def upsert_worldbook_activation(worldbook_id: str, *, global_active: bool, session_chat_ids: list[str]) -> None:
    wid = (worldbook_id or "").strip()
    if not wid:
        return
    with _index_lock:
        try:
            data = _load_index_unlocked()
        except Exception:
            data = _empty_index()
        data.setdefault("byId", {})[wid] = {
            "globalActive": bool(global_active),
            "sessionChatIds": [str(x).strip() for x in session_chat_ids if str(x).strip()],
        }
        data["rebuilt"] = True
        try:
            _write_index_unlocked(data)
        except Exception:
            global _index_dirty
            _index_dirty = True


def remove_worldbook_activation(worldbook_id: str) -> None:
    wid = (worldbook_id or "").strip()
    if not wid:
        return
    with _index_lock:
        try:
            data = _load_index_unlocked()
        except Exception:
            return
        if wid not in (data.get("byId") or {}):
            return
        data["byId"].pop(wid, None)
        try:
            _write_index_unlocked(data)
        except Exception:
            global _index_dirty
            _index_dirty = True


def list_active_worldbook_ids(chat_id: str, global_exclusions: set[str] | None = None) -> list[str]:
    """返回应对该会话激活的世界书 ID（不含正文）。"""
    global _index_dirty
    exclusions = global_exclusions or set()
    cid = (chat_id or "").strip()
    with _index_lock:
        if _index_dirty:
            data = rebuild_worldbook_index()
        else:
            try:
                data = _load_index_unlocked()
            except Exception:
                data = rebuild_worldbook_index()
            if not data.get("rebuilt"):
                data = rebuild_worldbook_index()
        by_id = data.get("byId") or {}
        out: list[str] = []
        for wid, entry in by_id.items():
            if not isinstance(entry, dict):
                continue
            if bool(entry.get("globalActive")):
                if wid in exclusions:
                    continue
                out.append(wid)
            elif cid and cid in (entry.get("sessionChatIds") or []):
                out.append(wid)
        return out
