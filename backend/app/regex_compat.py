"""
世界书正则兼容辅助：

- 保持存储的 regex 原样不变
- 仅在输入整体形如 /.../flags 且 flags 属于安全白名单时，按 JS 字面量拆壳
- Python 侧只映射可安全落地的 flags，避免静默改变语义
"""

from __future__ import annotations

import re

_SAFE_LITERAL_FLAG_MAP: dict[str, int] = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "u": 0,
}


def split_regex_literal(raw: str) -> tuple[str, int] | None:
    text = (raw or "").strip()
    if len(text) < 2 or not text.startswith("/"):
        return None

    in_class = False
    idx = 1
    while idx < len(text):
        ch = text[idx]
        if ch == "\\":
            idx += 2
            continue
        if ch == "[" and not in_class:
            in_class = True
            idx += 1
            continue
        if ch == "]" and in_class:
            in_class = False
            idx += 1
            continue
        if ch == "/" and not in_class:
            body = text[1:idx]
            suffix = text[idx + 1 :]
            if suffix and not suffix.isalpha():
                return None
            flags = 0
            seen: set[str] = set()
            for raw_flag in suffix.lower():
                if raw_flag in seen:
                    return None
                mapped = _SAFE_LITERAL_FLAG_MAP.get(raw_flag)
                if mapped is None:
                    return None
                seen.add(raw_flag)
                flags |= mapped
            return body, flags
        idx += 1
    return None


def compile_user_regex(raw: str, base_flags: int = 0) -> re.Pattern[str]:
    parsed = split_regex_literal(raw)
    if parsed is None:
        return re.compile((raw or "").strip(), base_flags)
    pattern, literal_flags = parsed
    return re.compile(pattern, base_flags | literal_flags)
