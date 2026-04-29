from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from app.content_regex import apply_content_regex_pipeline
from app.content_regex_queue import enqueue_content_regex_items
from app.storage import (
    list_characters,
    list_chats,
    list_group_chats,
    load_settings,
    save_chat,
)

_SCAN_INTERVAL_SECONDS = 0.5
_scanner_started = False
_scanner_lock = threading.Lock()
_processed_signatures: dict[tuple[str, str], str] = {}


def _resolve_effective_rules(chat: Any, settings: Any) -> list[Any]:
    global_rules = list(getattr(settings, "contentRegexRuleLibrary", None) or [])
    legacy_rules = list(getattr(getattr(chat, "overrides", None), "contentRegexRules", None) or [])
    enabled_map = dict(getattr(getattr(chat, "overrides", None), "contentRegexEnabledByRuleId", None) or {})
    source_rules = global_rules if global_rules else legacy_rules
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
        dirty = False
        for msg in chat.messages:
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
            if result.extracted_items:
                enqueue_content_regex_items(chat.id, result.extracted_items)
            next_display = result.display_text if result.display_text != msg.content else None
            if getattr(msg, "contentDisplay", None) != next_display:
                msg.contentDisplay = next_display
                dirty = True
        if dirty:
            chat.updatedAt = chat.updatedAt
            save_chat(chat)


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

