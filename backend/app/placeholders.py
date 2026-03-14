from __future__ import annotations

from typing import Iterable


def replace_placeholders_in_text(text: str, *, char_name: str, user_name: str) -> str:
    """只替换精确占位符 token。"""
    if not text:
        return text
    out = text
    if "{{char}}" in out:
        out = out.replace("{{char}}", char_name or "角色")
    if "{{user}}" in out:
        out = out.replace("{{user}}", user_name or "用户")
    return out


def replace_many(texts: Iterable[str], *, char_name: str, user_name: str) -> list[str]:
    return [replace_placeholders_in_text(t, char_name=char_name, user_name=user_name) for t in texts]

