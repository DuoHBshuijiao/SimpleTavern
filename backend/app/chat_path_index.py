"""
chatId → characterId / format 路径索引（T-803-3B）。

避免 `_find_chat_path_by_id` 在热路径上对角色目录做 O(C) exists 扫描。
不存绝对路径；由 characterId + chatId + format 推导。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Literal

ChatPathFormat = Literal["folder", "legacy"]

_INDEX_VERSION = 1
_index_lock = threading.RLock()
_index_dirty = False
_memory_cache: dict[str, Any] | None = None
_memory_mtime_ns: int | None = None


def _index_path() -> Path:
    from app.storage import _data_dir

    return _data_dir() / "chat_path_index.json"


def _empty_index() -> dict[str, Any]:
    return {
        "version": _INDEX_VERSION,
        "rebuilt": False,
        "byId": {},
    }


def _normalize_entry(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    character_id = str(raw.get("characterId") or "").strip()
    fmt = str(raw.get("format") or "folder").strip()
    if not character_id:
        return None
    if fmt not in {"folder", "legacy"}:
        fmt = "folder"
    return {"characterId": character_id, "format": fmt}


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
        raise RuntimeError(f"chat_path_index_read_failed: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("chat_path_index_corrupt: root must be object")
    by_id_raw = raw.get("byId")
    if by_id_raw is None:
        by_id_raw = {}
    if not isinstance(by_id_raw, dict):
        raise RuntimeError("chat_path_index_corrupt: byId must be object")
    by_id: dict[str, dict[str, str]] = {}
    for chat_id, entry in by_id_raw.items():
        cid = str(chat_id or "").strip()
        normalized = _normalize_entry(entry)
        if cid and normalized:
            by_id[cid] = normalized
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

    payload = {
        "version": _INDEX_VERSION,
        "rebuilt": bool(data.get("rebuilt")),
        "byId": dict(data.get("byId") or {}),
    }
    path = _index_path()
    write_json(path, payload)
    _memory_cache = payload
    try:
        _memory_mtime_ns = path.stat().st_mtime_ns
    except OSError:
        _memory_mtime_ns = None
    _index_dirty = False


def _paths_for_entry(chat_id: str, entry: dict[str, str]) -> tuple[Path, str]:
    from app.storage import chat_record_path, legacy_chat_path

    character_id = entry["characterId"]
    fmt = entry.get("format") or "folder"
    if fmt == "legacy":
        return legacy_chat_path(character_id, chat_id), character_id
    # folder 优先；若仅有 legacy 文件也兼容返回
    record = chat_record_path(character_id, chat_id)
    if record.exists():
        return record, character_id
    legacy = legacy_chat_path(character_id, chat_id)
    if legacy.exists():
        return legacy, character_id
    return record, character_id


def _scan_filesystem(chat_id: str) -> tuple[Path, str, ChatPathFormat] | None:
    from app.storage import CHAT_RECORD_FILENAME, _chats_dir

    base = _chats_dir()
    if not base.exists():
        return None
    for character_dir in base.iterdir():
        if not character_dir.is_dir():
            continue
        record_path = character_dir / chat_id / CHAT_RECORD_FILENAME
        if record_path.exists():
            return record_path, character_dir.name, "folder"
        legacy_path = character_dir / f"{chat_id}.json"
        if legacy_path.exists():
            return legacy_path, character_dir.name, "legacy"
    return None


def rebuild_chat_path_index() -> dict[str, Any]:
    """全库轻量重建：只枚举目录/文件名，不读 chat.json 正文。"""
    from app.storage import CHAT_RECORD_FILENAME, _chats_dir

    by_id: dict[str, dict[str, str]] = {}
    base = _chats_dir()
    if base.exists():
        for character_dir in base.iterdir():
            if not character_dir.is_dir():
                continue
            character_id = character_dir.name
            for entry in character_dir.iterdir():
                if entry.is_dir():
                    record = entry / CHAT_RECORD_FILENAME
                    if record.is_file():
                        by_id[entry.name] = {"characterId": character_id, "format": "folder"}
                elif entry.is_file() and entry.suffix == ".json":
                    chat_id = entry.stem
                    # 跳过已有 folder 格式的同名会话
                    if chat_id in by_id:
                        continue
                    if (character_dir / chat_id / CHAT_RECORD_FILENAME).exists():
                        continue
                    by_id[chat_id] = {"characterId": character_id, "format": "legacy"}
    data = {"version": _INDEX_VERSION, "rebuilt": True, "byId": by_id}
    with _index_lock:
        _write_index_unlocked(data)
    return data


def _load_or_rebuild_unlocked() -> dict[str, Any]:
    global _index_dirty
    if _index_dirty:
        return rebuild_chat_path_index()
    try:
        data = _load_index_unlocked()
    except Exception:
        return rebuild_chat_path_index()
    if not data.get("rebuilt"):
        return rebuild_chat_path_index()
    return data


def lookup_chat_path(chat_id: str) -> tuple[Path, str] | None:
    """
    解析 chatId → (record_path, characterId)。
    索引命中且文件存在则 O(1)；否则全角色扫描并回写索引。
    """
    cid = (chat_id or "").strip()
    if not cid:
        return None

    with _index_lock:
        try:
            data = _load_or_rebuild_unlocked()
        except Exception:
            data = _empty_index()
        entry = (data.get("byId") or {}).get(cid)
        if isinstance(entry, dict):
            path, character_id = _paths_for_entry(cid, entry)
            if path.exists():
                return path, character_id
            # stale：删掉坏条目后扫描
            data["byId"].pop(cid, None)
            try:
                _write_index_unlocked(data)
            except Exception:
                pass

    scanned = _scan_filesystem(cid)
    if scanned is None:
        return None
    path, character_id, fmt = scanned
    upsert_chat_path(cid, character_id, fmt)
    return path, character_id


def upsert_chat_path(chat_id: str, character_id: str, fmt: ChatPathFormat = "folder") -> None:
    cid = (chat_id or "").strip()
    char = (character_id or "").strip()
    if not cid or not char:
        return
    with _index_lock:
        try:
            data = _load_or_rebuild_unlocked()
        except Exception:
            data = _empty_index()
            data["rebuilt"] = True
        data.setdefault("byId", {})[cid] = {"characterId": char, "format": fmt}
        data["rebuilt"] = True
        try:
            _write_index_unlocked(data)
        except Exception:
            global _index_dirty
            _index_dirty = True


def remove_chat_path(chat_id: str) -> None:
    cid = (chat_id or "").strip()
    if not cid:
        return
    with _index_lock:
        try:
            data = _load_or_rebuild_unlocked()
        except Exception:
            return
        if cid not in (data.get("byId") or {}):
            return
        data["byId"].pop(cid, None)
        try:
            _write_index_unlocked(data)
        except Exception:
            global _index_dirty
            _index_dirty = True


def remove_chats_for_character(character_id: str) -> None:
    char = (character_id or "").strip()
    if not char:
        return
    with _index_lock:
        try:
            data = _load_or_rebuild_unlocked()
        except Exception:
            return
        by_id = data.get("byId") or {}
        remove_ids = [cid for cid, entry in by_id.items() if entry.get("characterId") == char]
        if not remove_ids:
            return
        for cid in remove_ids:
            by_id.pop(cid, None)
        data["byId"] = by_id
        try:
            _write_index_unlocked(data)
        except Exception:
            global _index_dirty
            _index_dirty = True


def warm_chat_path_index() -> dict[str, Any]:
    """启动预热：确保索引 rebuilt。"""
    with _index_lock:
        return _load_or_rebuild_unlocked()


def measure_lookup_batch(chat_ids: list[str]) -> float:
    """测试辅助：连续 lookup 的毫秒耗时。"""
    started = time.perf_counter()
    for chat_id in chat_ids:
        lookup_chat_path(chat_id)
    return (time.perf_counter() - started) * 1000
