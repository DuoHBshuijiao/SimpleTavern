"""
分叉溯源索引：避免 fork-lineage 全库 read_json 与 load_chat(超长源会话)。
"""

from __future__ import annotations

import json
import threading
from typing import Any

from app.errors import AppError
from app.schemas import (
    Chat,
    ForkLineageResponse,
    ForkLineageWarning,
    ForkOrigin,
    ForkOutgoingGroup,
    ForkSiblingSummary,
)
from app.services.cleanup_log import log_cleanup_failure
from app.storage import (
    CHAT_RECORD_FILENAME,
    ForkChatSummary,
    _chats_dir,
    _data_dir,
    _find_chat_path_by_id,
    load_chat,
    read_chat_fork_meta,
    read_json,
    write_json,
)

_INDEX_VERSION = 1
_index_lock = threading.RLock()
_pending_warnings: list[ForkLineageWarning] = []
_index_dirty = False


class ForkIndexLoadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _record_warning(
    code: str,
    message: str,
    suggested_action: str,
) -> None:
    with _index_lock:
        if any(item.code == code for item in _pending_warnings):
            return
        _pending_warnings.append(
            ForkLineageWarning(
                code=code,
                message=message,
                suggestedAction=suggested_action,
            )
        )
        del _pending_warnings[:-20]


def _consume_warnings() -> list[ForkLineageWarning]:
    with _index_lock:
        warnings = list(_pending_warnings)
        _pending_warnings.clear()
        return warnings


def _fork_index_path() -> Path:
    return _data_dir() / "fork_index.json"


def _empty_index() -> dict[str, Any]:
    return {
        "version": _INDEX_VERSION,
        "rebuilt": False,
        "forkCharacterIds": [],
        "byParent": {},
        "byChild": {},
        "titles": {},
        "warnings": [],
    }


def _load_index_unlocked() -> dict[str, Any]:
    path = _fork_index_path()
    if not path.is_file():
        return _empty_index()
    try:
        raw = read_json(path)
    except Exception as exc:
        code = "fork_index_corrupt" if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else "fork_index_read_failed"
        raise ForkIndexLoadError(code, f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ForkIndexLoadError("fork_index_corrupt", "fork index root must be an object")
    raw.setdefault("version", _INDEX_VERSION)
    raw.setdefault("rebuilt", False)
    raw.setdefault("forkCharacterIds", [])
    raw.setdefault("byParent", {})
    raw.setdefault("byChild", {})
    raw.setdefault("titles", {})
    raw.setdefault("warnings", [])
    if not isinstance(raw["forkCharacterIds"], list):
        raise ForkIndexLoadError("fork_index_corrupt", "forkCharacterIds must be an array")
    for key in ("byParent", "byChild", "titles"):
        if not isinstance(raw[key], dict):
            raise ForkIndexLoadError("fork_index_corrupt", f"{key} must be an object")
    if not isinstance(raw["warnings"], list):
        raise ForkIndexLoadError("fork_index_corrupt", "warnings must be an array")
    try:
        raw["warnings"] = [
            ForkLineageWarning.model_validate(item).model_dump(mode="json")
            for item in raw["warnings"]
        ]
    except Exception as exc:
        raise ForkIndexLoadError("fork_index_corrupt", f"invalid warning entry: {exc}") from exc
    return raw


def _load_or_rebuild_index_unlocked() -> dict[str, Any]:
    global _index_dirty
    if _index_dirty:
        rebuild_fork_index()
        return _load_index_unlocked()
    try:
        data = _load_index_unlocked()
    except ForkIndexLoadError as exc:
        log_cleanup_failure(
            source="fork_index.load",
            exc=exc,
            path=_fork_index_path(),
        )
        _record_warning(
            exc.code,
            "分叉索引损坏，已从会话文件重建" if exc.code == "fork_index_corrupt" else "分叉索引读取失败，已尝试重建",
            "如该提示重复出现，请运行数据完整性巡检并检查 data/fork_index.json",
        )
        rebuild_fork_index()
        return _load_index_unlocked()
    if _index_needs_rebuild(data):
        rebuild_fork_index()
        return _load_index_unlocked()
    return data


def _index_needs_rebuild(data: dict[str, Any]) -> bool:
    return data.get("version") != _INDEX_VERSION or not bool(data.get("rebuilt"))


def _save_index_unlocked(data: dict[str, Any]) -> None:
    path = _fork_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = _INDEX_VERSION
    data["rebuilt"] = True
    write_json(path, data)


def _sibling_from_entry(entry: dict[str, Any]) -> ForkSiblingSummary:
    return ForkSiblingSummary(
        chatId=str(entry.get("chatId") or ""),
        title=str(entry.get("title") or "新对话"),
        createdAt=str(entry.get("createdAt") or ""),
    )


def sync_chat_fork_index(chat: Chat) -> None:
    """save_chat / delete 后同步单条会话的分叉索引。"""
    global _index_dirty
    try:
        with _index_lock:
            data = _load_or_rebuild_index_unlocked()
            chat_id = chat.id
            titles: dict[str, str] = data["titles"]
            titles[chat_id] = (chat.title or "").strip() or "新对话"

            by_child: dict[str, Any] = data["byChild"]
            old_child = by_child.pop(chat_id, None)
            if old_child:
                _remove_from_by_parent(
                    data["byParent"],
                    str(old_child.get("parentChatId") or ""),
                    str(old_child.get("messageId") or ""),
                    chat_id,
                )

            parent_id = (chat.forkedFromChatId or "").strip() or None
            msg_id = (chat.forkedFromMessageId or "").strip() or None
            if parent_id and msg_id:
                idx = chat.forkedFromMessageIndex
                by_child[chat_id] = {
                    "chatId": chat_id,
                    "parentChatId": parent_id,
                    "messageId": msg_id,
                    "messageIndex": idx,
                    "title": titles[chat_id],
                    "createdAt": chat.createdAt or "",
                }
                entry = {
                    "chatId": chat_id,
                    "title": titles[chat_id],
                    "createdAt": chat.createdAt or "",
                    "anchorMessageIndex": idx,
                }
                _upsert_by_parent(data["byParent"], parent_id, msg_id, entry)
                fork_character_ids = set(data.get("forkCharacterIds") or [])
                fork_character_ids.add(chat.characterId)
                data["forkCharacterIds"] = sorted(fork_character_ids)

            _save_index_unlocked(data)
    except Exception as exc:
        _index_dirty = True
        _record_warning(
            "fork_index_sync_failed",
            "会话已保存，但分叉索引同步失败",
            "重新打开分叉信息以触发重建；如持续失败请检查 data 目录权限",
        )
        log_cleanup_failure(
            source="fork_index.sync",
            exc=exc,
            path=_fork_index_path(),
        )


def remove_chat_fork_index(chat_id: str) -> None:
    global _index_dirty
    try:
        with _index_lock:
            data = _load_or_rebuild_index_unlocked()
            data["titles"].pop(chat_id, None)
            old_child = data["byChild"].pop(chat_id, None)
            if old_child:
                _remove_from_by_parent(
                    data["byParent"],
                    str(old_child.get("parentChatId") or ""),
                    str(old_child.get("messageId") or ""),
                    chat_id,
                )
            for parent_id, by_msg in list(data.get("byParent", {}).items()):
                for msg_id, entries in list(by_msg.items()):
                    filtered = [e for e in entries if str(e.get("chatId")) != chat_id]
                    if filtered:
                        by_msg[msg_id] = filtered
                    else:
                        del by_msg[msg_id]
                if not by_msg:
                    del data["byParent"][parent_id]
            _save_index_unlocked(data)
    except Exception as exc:
        _index_dirty = True
        _record_warning(
            "fork_index_sync_failed",
            "会话已删除，但分叉索引清理失败",
            "重新打开分叉信息以触发重建；如持续失败请检查 data 目录权限",
        )
        log_cleanup_failure(
            source="fork_index.remove",
            exc=exc,
            path=_fork_index_path(),
        )


def _upsert_by_parent(
    by_parent: dict[str, Any],
    parent_id: str,
    message_id: str,
    entry: dict[str, Any],
) -> None:
    parent_bucket = by_parent.setdefault(parent_id, {})
    entries: list[dict[str, str]] = list(parent_bucket.get(message_id) or [])
    chat_id = entry["chatId"]
    for i, e in enumerate(entries):
        if str(e.get("chatId")) == chat_id:
            entries[i] = entry
            parent_bucket[message_id] = entries
            return
    entries.append(entry)
    parent_bucket[message_id] = entries


def _remove_from_by_parent(
    by_parent: dict[str, Any],
    parent_id: str,
    message_id: str,
    chat_id: str,
) -> None:
    if not parent_id or not message_id:
        return
    parent_bucket = by_parent.get(parent_id)
    if not parent_bucket:
        return
    entries = parent_bucket.get(message_id)
    if not entries:
        return
    filtered = [e for e in entries if str(e.get("chatId")) != chat_id]
    if filtered:
        parent_bucket[message_id] = filtered
    else:
        del parent_bucket[message_id]
        if not parent_bucket:
            del by_parent[parent_id]


def _resolve_anchor_index(
    parent_chat_id: str,
    message_id: str,
    cache: dict[str, dict[str, int] | None],
) -> int | None:
    if parent_chat_id not in cache:
        try:
            parent = load_chat(parent_chat_id)
        except FileNotFoundError:
            cache[parent_chat_id] = None
        except AppError as exc:
            _record_warning(
                "fork_meta_unreadable",
                "部分分叉锚点因源会话损坏而无法恢复",
                "运行数据完整性巡检并修复对应会话后重新加载",
            )
            log_cleanup_failure(
                source="fork_index.resolve_anchor",
                exc=exc,
                path=parent_chat_id,
            )
            cache[parent_chat_id] = None
        else:
            cache[parent_chat_id] = {m.id: i + 1 for i, m in enumerate(parent.messages)}
    index_by_message = cache.get(parent_chat_id)
    if not index_by_message:
        return None
    return index_by_message.get(message_id)


def rebuild_fork_index(character_ids: set[str] | None = None) -> None:
    """
    冷启动：轻量 meta 扫描重建索引。

    若未指定 character_ids，先用尾部 fork 元数据找出真正存在 fork 子会话的角色；
    第二遍只索引这些角色，避免把“索引修复”扩散到所有角色的完整元数据处理。
    """
    global _index_dirty
    with _index_lock:
        data = _empty_index()
        titles: dict[str, str] = data["titles"]
        by_parent: dict[str, Any] = data["byParent"]
        by_child: dict[str, Any] = data["byChild"]

        base = _chats_dir()
        summaries_by_character: dict[str, list[ForkChatSummary]] = {}
        fork_character_ids: set[str] = set(character_ids or set())
        incomplete = False
        if base.exists():
            for character_dir in base.iterdir():
                if not character_dir.is_dir():
                    continue
                cid = character_dir.name
                for entry in character_dir.iterdir():
                    if not entry.is_dir():
                        continue
                    record_path = entry / CHAT_RECORD_FILENAME
                    if not record_path.is_file():
                        continue
                    summary = read_chat_fork_meta(record_path)
                    if summary is None:
                        incomplete = True
                        _record_warning(
                            "fork_meta_unreadable",
                            "部分会话的分叉元数据无法读取，索引结果可能不完整",
                            "运行数据完整性巡检并修复对应会话后重新加载",
                        )
                        continue
                    summaries_by_character.setdefault(cid, []).append(summary)
                    if summary.forkedFromChatId and summary.forkedFromMessageId:
                        fork_character_ids.add(cid)

        data["forkCharacterIds"] = sorted(fork_character_ids)
        parent_index_cache: dict[str, dict[str, int] | None] = {}
        for cid in sorted(fork_character_ids):
            for summary in summaries_by_character.get(cid, []):
                titles[summary.id] = summary.title
                parent_id = summary.forkedFromChatId
                msg_id = summary.forkedFromMessageId
                if parent_id and msg_id:
                    anchor_idx = summary.forkedFromMessageIndex or _resolve_anchor_index(
                        parent_id,
                        msg_id,
                        parent_index_cache,
                    )
                    by_child[summary.id] = {
                        "chatId": summary.id,
                        "parentChatId": parent_id,
                        "messageId": msg_id,
                        "messageIndex": anchor_idx,
                        "title": summary.title,
                        "createdAt": summary.createdAt,
                    }
                    _upsert_by_parent(
                        by_parent,
                        parent_id,
                        msg_id,
                        {
                            "chatId": summary.id,
                            "title": summary.title,
                            "createdAt": summary.createdAt,
                                "anchorMessageIndex": anchor_idx,
                        },
                    )

        if incomplete:
            data["warnings"] = [
                ForkLineageWarning(
                    code="fork_meta_unreadable",
                    message="部分会话的分叉元数据无法读取，索引结果可能不完整",
                    suggestedAction="运行数据完整性巡检并修复对应会话后重新加载",
                ).model_dump(mode="json")
            ]
        _save_index_unlocked(data)
        _index_dirty = False


def _resolve_parent_title(parent_chat_id: str, index: dict[str, Any]) -> str:
    titles: dict[str, str] = index.get("titles") or {}
    title = (titles.get(parent_chat_id) or "").strip()
    if title:
        return title
    found = _find_chat_path_by_id(parent_chat_id)
    if found is None:
        return "已删除的会话"
    meta = read_chat_fork_meta(found[0])
    if meta is None:
        return "已删除的会话"
    titles[parent_chat_id] = meta.title
    return meta.title


def _coerce_positive_int(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def build_fork_lineage(chat_id: str) -> ForkLineageResponse:
    """由索引构建 ForkLineageResponse；不加载 chat.json 的 messages。"""
    try:
        with _index_lock:
            data = _load_or_rebuild_index_unlocked()
    except Exception as exc:
        raise AppError(
            code="fork_index_rebuild_failed",
            message="分叉索引无法读取或重建",
            detail=f"{type(exc).__name__}: {exc}",
            source="fork_index.lineage",
            status_code=503,
            retryable=True,
            suggested_action="检查 data 目录读写权限后重试，或从备份恢复损坏的会话文件",
        ) from exc

    origin: ForkOrigin | None = None
    siblings: list[ForkSiblingSummary] = []
    child_rec = (data.get("byChild") or {}).get(chat_id) or {}
    src_chat_id = str(child_rec.get("parentChatId") or "").strip() or None
    src_msg_id = str(child_rec.get("messageId") or "").strip() or None

    if src_chat_id and src_msg_id:
        idx = _coerce_positive_int(child_rec.get("messageIndex")) or 1
        origin = ForkOrigin(
            chatId=src_chat_id,
            title=_resolve_parent_title(src_chat_id, data),
            messageId=src_msg_id,
            messageIndex=int(idx),
        )

        parent_bucket = (data.get("byParent") or {}).get(src_chat_id) or {}
        for entry in parent_bucket.get(src_msg_id) or []:
            if str(entry.get("chatId")) == chat_id:
                continue
            siblings.append(_sibling_from_entry(entry))

    outgoing_forks: list[ForkOutgoingGroup] = []
    current_bucket = (data.get("byParent") or {}).get(chat_id) or {}
    for mid, entries in current_bucket.items():
        idx = next(
            (
                n
                for e in entries
                for n in [_coerce_positive_int(e.get("anchorMessageIndex"))]
                if n is not None
            ),
            None,
        )
        if idx is None:
            continue
        chats = sorted(
            [_sibling_from_entry(e) for e in entries],
            key=lambda c: c.createdAt,
            reverse=True,
        )
        outgoing_forks.append(
            ForkOutgoingGroup(
                messageId=mid,
                messageIndex=idx,
                count=len(chats),
                chats=chats,
            )
        )

    outgoing_forks.sort(key=lambda g: g.messageIndex)
    siblings.sort(key=lambda c: c.createdAt, reverse=True)

    warnings = _consume_warnings()
    for raw_warning in data.get("warnings") or []:
        warning = ForkLineageWarning.model_validate(raw_warning)
        if not any(item.code == warning.code for item in warnings):
            warnings.append(warning)
    return ForkLineageResponse(
        origin=origin,
        siblings=siblings,
        outgoingForks=outgoing_forks,
        partialSuccess=bool(warnings),
        warnings=warnings,
    )
