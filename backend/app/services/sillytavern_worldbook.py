from __future__ import annotations

import re
from typing import Any

import regex

from app.regex_compat import compile_timed_user_regex, split_regex_literal
from app.schemas import WorldBook


def build_worldbook(card_name: str, raw_data: dict[str, Any], warnings: list[str] | None = None) -> WorldBook | None:
    character_book = raw_data.get("character_book")
    if not isinstance(character_book, dict) or not isinstance(character_book.get("entries"), list):
        return None
    entries = []
    for index, raw in enumerate(character_book["entries"]):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("comment") or "").strip() or f"条目 {index + 1}"
        try:
            order = int(raw.get("insertion_order", index))
        except (TypeError, ValueError):
            order = index
        expression, invalid = _entry_regex(raw)
        if invalid and warnings is not None:
            warnings.append(f"世界书「{title}」有 {invalid} 个无法转换的正则关键词，已跳过")
        entries.append({
            "title": title,
            "content": str(raw.get("content") or "").strip(),
            "enabled": bool(raw.get("enabled", True)) and (bool(expression) or not invalid),
            "orderIndex": order,
            "regex": expression,
        })
    if not entries:
        return None
    name = str(character_book.get("name") or "").strip() or f"{card_name or '角色'} 世界书"
    return WorldBook(name=name, entries=entries)


def _entry_regex(raw: dict[str, Any]) -> tuple[str, int]:
    if raw.get("constant"):
        return ".*", 0
    keys = raw.get("keys")
    if not isinstance(keys, list):
        return "", 0
    extensions = raw.get("extensions") if isinstance(raw.get("extensions"), dict) else {}
    case_sensitive = bool(raw.get("case_sensitive", extensions.get("case_sensitive", False)))
    alternatives: list[str] = []
    invalid = 0
    has_numbered_reference = False
    for key in keys:
        if not isinstance(key, str) or not key.strip():
            continue
        key = key.strip()
        modifiers = "" if case_sensitive else "i"
        literal = re.fullmatch(r"(/.+/)([a-z]*)", key, re.DOTALL | re.IGNORECASE)
        if literal:
            delimiter, flags = literal.groups()
            flags = flags.lower().replace("g", "").replace("d", "")
            parsed = split_regex_literal(delimiter + flags)
            if parsed is None:
                invalid += 1
                continue
            pattern = parsed[0]
            modifiers = "".join(flag for flag in flags if flag in "ims")
        elif raw.get("use_regex"):
            pattern = key
            inline_flags = re.match(r"\(\?([ims]+)\)", pattern)
            if inline_flags:
                modifiers = "".join(dict.fromkeys(modifiers + inline_flags.group(1)))
                pattern = pattern[inline_flags.end():]
        else:
            pattern = re.escape(key)
        alternative = f"(?{modifiers}:{pattern})"
        try:
            compile_timed_user_regex(alternative)
        except regex.error:
            invalid += 1
            continue
        alternatives.append(alternative)
        has_numbered_reference |= bool(re.search(r"\\[1-9]", pattern))
    if not alternatives:
        return "", invalid
    if len(alternatives) > 1 and has_numbered_reference:
        return "(?|" + "|".join(alternatives) + ")", invalid
    return "|".join(alternatives), invalid
