from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from app.content_regex import apply_content_regex_pipeline
from app.content_regex_queue import enqueue_content_regex_items
from app.group_mvu import is_chat_mvu_runtime_enabled
from app.storage import (
    list_characters,
    list_chats,
    list_group_chats,
    load_settings,
)
    # 扫描间隔时间，之前出于性能考虑从0.5s改为5s，但实际进行性能检查后发现前端渲染瓶颈不在于此，因此改为0.5s
_SCAN_INTERVAL_SECONDS = 0.5
_scanner_started = False
_scanner_lock = threading.Lock()
_processed_signatures: dict[tuple[str, str], str] = {}


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
    yielded: set[str] = set()
    for chat in list_group_chats():
        yielded.add(chat.id)
        yield chat
    for c in list_characters():
        for chat in list_chats(c.id):
            if chat.id in yielded:
                continue
            yielded.add(chat.id)
            yield chat


def _scan_once() -> None:
    settings = load_settings()
    for chat in _chat_iter():
        rules = _resolve_effective_rules(chat, settings)
        if not rules:
            continue
        rules_sig = _rules_signature(rules)

        # 检查会话是否启用 MVU（单聊看角色卡；群聊看显式开关与兼容逻辑）
        mvu_enabled = is_chat_mvu_runtime_enabled(chat)

        # 定位 MVU 已消费标记所在的消息索引（-1 表示无标记）
        last_processed_idx: int = -1
        if mvu_enabled:
            for i in range(len(chat.messages) - 1, -1, -1):
                if getattr(chat.messages[i], "mvuProcessed", False):
                    last_processed_idx = i
                    break

        # 找到最新一条有效消息（assistant/user，有内容）的索引
        last_valid_idx: int = -1
        for i in range(len(chat.messages) - 1, -1, -1):
            msg = chat.messages[i]
            if msg.role in ("assistant", "user") and (msg.content or "").strip():
                last_valid_idx = i
                break

        for idx, msg in enumerate(chat.messages):
            if msg.role not in ("assistant", "user"):
                continue
            content = (msg.content or "").strip()
            if not content:
                continue
            key = (chat.id, msg.id)
            sig_raw = f"{msg.content}|{rules_sig}"
            msg_sig = hashlib.sha1(sig_raw.encode("utf-8")).hexdigest()
            if _processed_signatures.get(key) == msg_sig:
                continue
            _processed_signatures[key] = msg_sig
            result = apply_content_regex_pipeline(msg.content, rules)

            # MVU 入队：仅当角色开启 MVU 且消息符合过滤条件
            if mvu_enabled and result.extracted_items:
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


def _scanner_loop() -> None:
    while True:
        try:
            _scan_once()
        except Exception:
            pass
        time.sleep(_SCAN_INTERVAL_SECONDS)


def ensure_content_regex_scanner_started() -> None:
    global _scanner_started
    with _scanner_lock:
        if _scanner_started:
            return
        t = threading.Thread(target=_scanner_loop, name="content-regex-scanner", daemon=True)
        t.start()
        _scanner_started = True

