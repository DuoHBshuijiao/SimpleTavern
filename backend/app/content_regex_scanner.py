from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.content_regex import apply_content_regex_pipeline
from app.content_regex_queue import enqueue_content_regex_items, get_content_regex_queue_dropped
from app.errors import AppError, as_app_error
from app.group_mvu import resolve_chat_mvu_runtime_enablement
from app.storage import (
    _load_chat_from_path,
    character_path,
    get_lock_observability,
    iter_chat_record_paths,
    load_character,
    load_settings,
)
from app.worker_health import WorkerHealth

logger = logging.getLogger(__name__)

_SCAN_INTERVAL_SECONDS = 5.0
_SCAN_DEPTH_HARD_LIMIT = 50
_FAILURE_PAUSE_AFTER = 5
_scanner_started = False
_scanner_lock = threading.Lock()
_scan_run_lock = threading.Lock()
_processed_signatures: dict[tuple[str, str], str] = {}
_scan_cache: dict[str, dict[str, Any]] = {}
_last_scan_stats: dict[str, Any] = {
    "lastScanDurationMs": 0.0,
    "chatsConsidered": 0,
    "chatsLoaded": 0,
    "chatsSkippedUnchanged": 0,
    "messagesScanned": 0,
    "messagesApplied": 0,
}
_scanner_health = WorkerHealth()


def get_content_regex_scanner_health() -> dict:
    """返回正文正则 scanner 全局 health。"""
    lock_stats = get_lock_observability()
    _scanner_health.extras = {
        "queueDroppedTotal": get_content_regex_queue_dropped(),
        "scannerStarted": _scanner_started,
        **_last_scan_stats,
        "lockWaitMsTotal": lock_stats.get("waitMsTotal"),
        "lockWaitMsMax": lock_stats.get("waitMsMax"),
        "lockAcquireCount": lock_stats.get("acquireCount"),
        "lockSharedAcquireCount": lock_stats.get("sharedAcquireCount"),
    }
    return _scanner_health.to_dict()


def reset_scanner_scan_state_for_tests() -> None:
    """测试辅助：清空消息签名与 mtime 缓存。"""
    _processed_signatures.clear()
    _scan_cache.clear()
    _last_scan_stats.update(
        {
            "lastScanDurationMs": 0.0,
            "chatsConsidered": 0,
            "chatsLoaded": 0,
            "chatsSkippedUnchanged": 0,
            "messagesScanned": 0,
            "messagesApplied": 0,
        }
    )


def _resolve_effective_rules(chat: Any, settings: Any) -> list[Any]:
    global_rules = list(getattr(settings, "contentRegexRuleLibrary", None) or [])
    legacy_rules = list(getattr(getattr(chat, "overrides", None), "contentRegexRules", None) or [])
    enabled_map = dict(getattr(getattr(chat, "overrides", None), "contentRegexEnabledByRuleId", None) or {})
    # 合并全局规则库与会话级角色规则，同 ID 以全局为准
    seen_ids: set[str] = set()
    merged: list[Any] = []
    for r in global_rules:
        merged.append(r)
        seen_ids.add(str(getattr(r, "id", "")))
    for r in legacy_rules:
        rid = str(getattr(r, "id", ""))
        if rid not in seen_ids:
            merged.append(r)
            seen_ids.add(rid)
    source_rules = merged
    out: list[Any] = []
    for r in source_rules:
        cp = r.model_copy(deep=True)
        rid = str(getattr(cp, "id", ""))
        if rid and rid in enabled_map:
            cp.enabled = bool(enabled_map[rid])
        out.append(cp)
    return out


def _rules_signature(rules: list[Any]) -> str:
    raw = [
        {
            "id": str(getattr(r, "id", "")),
            "enabled": bool(getattr(r, "enabled", True)),
            "order": int(getattr(r, "order", 0)),
            "pattern": str(getattr(r, "pattern", "")),
            "action": str(getattr(r, "action", "")),
            "replacement": str(getattr(r, "replacement", "")),
            "matchMode": str(getattr(r, "matchMode", "")),
            "extractSource": str(getattr(r, "extractSource", "")),
            "extractGroupIndex": getattr(r, "extractGroupIndex", None),
        }
        for r in rules
    ]
    return hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _chat_iter():
    """兼容旧测试：逐会话 yield 全量 Chat（单次枚举，无群聊双载）。"""
    for character_id, _chat_id, path in iter_chat_record_paths():
        chat = _load_chat_from_path(path, character_id, shared=True, attach_memory=False)
        if chat is not None:
            yield chat


def _scan_depth(chat: Any, rules: list[Any]) -> int:
    overrides = getattr(chat, "overrides", None)
    depth = getattr(overrides, "contentRegexScanDepthDefault", None)
    if not isinstance(depth, int) or depth < 1:
        depth = _SCAN_DEPTH_HARD_LIMIT
    for rule in rules:
        override = getattr(rule, "scanDepthOverride", None)
        if isinstance(override, int) and override >= 1:
            depth = max(depth, override)
    return max(1, min(_SCAN_DEPTH_HARD_LIMIT, depth))


def _scannable_message_indexes(chat: Any, rules: list[Any]) -> set[int]:
    depth = _scan_depth(chat, rules)
    indexes: list[int] = []
    for idx in range(len(chat.messages) - 1, -1, -1):
        msg = chat.messages[idx]
        if msg.role not in ("assistant", "user"):
            continue
        if not (msg.content or "").strip():
            continue
        indexes.append(idx)
        if len(indexes) >= depth:
            break
    return set(indexes)


def _character_mtime_ns(character_id: str) -> int:
    try:
        path = character_path(character_id)
        if path.exists():
            return int(path.stat().st_mtime_ns)
    except OSError:
        return 0
    return 0


def _resolve_chat_mvu_scan_mode(chat: Any, character_cache: dict[str, Any]) -> str:
    """Return the MVU mode relevant to regex scanner enqueue behavior."""
    overrides = getattr(chat, "overrides", None)
    override_mode = getattr(overrides, "mvuMode", None) if overrides is not None else None
    if override_mode in ("regex", "directive"):
        return str(override_mode)
    character_id = str(getattr(chat, "characterId", "") or "")
    character = character_cache.get(character_id)
    if character is None:
        try:
            character = load_character(character_id)
        except Exception:
            return "regex"
        character_cache[character_id] = character
    character_mode = getattr(character, "mvuMode", None)
    return str(character_mode) if character_mode in ("regex", "directive") else "regex"


def _process_chat(chat: Any, settings: Any, character_cache: dict[str, Any]) -> tuple[int, int]:
    """扫描单会话；返回 (messages_scanned, messages_applied)。"""
    rules = _resolve_effective_rules(chat, settings)
    if not rules:
        return 0, 0
    rules_sig = _rules_signature(rules)

    enablement = resolve_chat_mvu_runtime_enablement(chat)
    mvu_enabled = enablement.enabled and enablement.character_error is None
    mvu_mode = _resolve_chat_mvu_scan_mode(chat, character_cache) if mvu_enabled else "regex"

    last_processed_idx: int = -1
    if mvu_enabled:
        for i in range(len(chat.messages) - 1, -1, -1):
            if getattr(chat.messages[i], "mvuProcessed", False):
                last_processed_idx = i
                break

    scannable_indexes = _scannable_message_indexes(chat, rules)

    last_valid_idx: int = -1
    for i in range(len(chat.messages) - 1, -1, -1):
        msg = chat.messages[i]
        if msg.role in ("assistant", "user") and (msg.content or "").strip():
            last_valid_idx = i
            break

    scanned = 0
    applied = 0
    for idx, msg in enumerate(chat.messages):
        if idx not in scannable_indexes:
            continue
        if msg.role not in ("assistant", "user"):
            continue
        if idx == 0 and msg.role == "assistant":
            continue
        content = (msg.content or "").strip()
        if not content:
            continue
        scanned += 1
        key = (chat.id, msg.id)
        sig_raw = f"{msg.content}|{rules_sig}"
        msg_sig = hashlib.sha1(sig_raw.encode("utf-8")).hexdigest()
        if _processed_signatures.get(key) == msg_sig:
            continue
        result = apply_content_regex_pipeline(msg.content, rules)
        applied += 1

        if mvu_enabled and mvu_mode == "regex" and result.extracted_items:
            should_enqueue = False
            if last_processed_idx >= 0:
                if idx > last_processed_idx:
                    should_enqueue = True
            else:
                if idx == last_valid_idx:
                    should_enqueue = True

            if should_enqueue:
                for item in result.extracted_items:
                    item["messageId"] = msg.id
                enqueue_content_regex_items(chat.id, result.extracted_items)
                from app.services.mvu_daemon import signal_queue_threshold

                signal_queue_threshold(chat.id)

        # 成功跑完 apply/enqueue 后再记签名，失败时可在下轮重试
        _processed_signatures[key] = msg_sig
    return scanned, applied


def _scan_once() -> dict[str, Any]:
    with _scan_run_lock:
        return _scan_once_unlocked()


def _scan_once_unlocked() -> dict[str, Any]:
    started = time.perf_counter()
    considered = 0
    loaded = 0
    skipped = 0
    messages_scanned = 0
    messages_applied = 0
    seen_paths: set[str] = set()
    character_cache: dict[str, Any] = {}

    settings = load_settings()
    global_rules_sig = _rules_signature(list(getattr(settings, "contentRegexRuleLibrary", None) or []))

    for character_id, _chat_id, path in iter_chat_record_paths():
        considered += 1
        cache_key = str(path)
        seen_paths.add(cache_key)
        try:
            st = path.stat()
            mtime_ns = int(st.st_mtime_ns)
            size = int(st.st_size)
        except OSError:
            continue
        char_mtime = _character_mtime_ns(character_id)
        cached = _scan_cache.get(cache_key)
        if (
            cached
            and cached.get("mtime_ns") == mtime_ns
            and cached.get("size") == size
            and cached.get("globalRulesSig") == global_rules_sig
            and cached.get("characterMtimeNs") == char_mtime
        ):
            skipped += 1
            continue

        chat = _load_chat_from_path(path, character_id, shared=True, attach_memory=False)
        if chat is None:
            _scan_cache.pop(cache_key, None)
            continue
        loaded += 1
        scanned, applied = _process_chat(chat, settings, character_cache)
        messages_scanned += scanned
        messages_applied += applied
        _scan_cache[cache_key] = {
            "mtime_ns": mtime_ns,
            "size": size,
            "globalRulesSig": global_rules_sig,
            "characterMtimeNs": char_mtime,
        }

    # 清理已删除会话的缓存与消息签名
    stale_keys = [k for k in _scan_cache if k not in seen_paths]
    for k in stale_keys:
        _scan_cache.pop(k, None)
    if seen_paths:
        alive_chat_ids = {
            Path(p).parent.name if Path(p).name == "chat.json" else Path(p).stem for p in seen_paths
        }
        stale_sigs = [key for key in _processed_signatures if key[0] not in alive_chat_ids]
        for key in stale_sigs:
            _processed_signatures.pop(key, None)

    stats = {
        "lastScanDurationMs": round((time.perf_counter() - started) * 1000.0, 3),
        "chatsConsidered": considered,
        "chatsLoaded": loaded,
        "chatsSkippedUnchanged": skipped,
        "messagesScanned": messages_scanned,
        "messagesApplied": messages_applied,
    }
    _last_scan_stats.update(stats)
    return stats


def _scanner_loop() -> None:
    while True:
        sleep_seconds = _SCAN_INTERVAL_SECONDS
        if _scanner_health.paused and _scanner_health.next_retry_at:
            try:
                retry_ts = datetime.fromisoformat(_scanner_health.next_retry_at).timestamp()
            except ValueError:
                retry_ts = 0.0
            remaining = retry_ts - time.time()
            if remaining > 0:
                time.sleep(min(60.0, remaining))
                continue
            _scanner_health.paused = False
            _scanner_health.status = "degraded"
        try:
            _scan_once()
            _scanner_health.record_success()
        except Exception as exc:
            logger.exception("content regex scanner failed")
            error = as_app_error(
                exc,
                source="content_regex.scanner",
                default_code="content_regex_scanner_failed",
                default_message="正文正则扫描失败",
            )
            backoff = min(60.0, _SCAN_INTERVAL_SECONDS * max(1, _scanner_health.failure_count + 1))
            _scanner_health.record_failure(
                error,
                pause_after=_FAILURE_PAUSE_AFTER,
                retry_after_seconds=backoff,
            )
            sleep_seconds = backoff
        time.sleep(sleep_seconds)


def ensure_content_regex_scanner_started() -> None:
    global _scanner_started
    with _scanner_lock:
        if _scanner_started:
            return
        t = threading.Thread(target=_scanner_loop, name="content-regex-scanner", daemon=True)
        t.start()
        _scanner_started = True
