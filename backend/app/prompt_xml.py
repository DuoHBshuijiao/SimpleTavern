"""System prompt 中注入段落的 XML 包裹与转义（与 replace_placeholders 组合使用）。"""

from __future__ import annotations

import html

from app.placeholders import replace_placeholders_in_text


def escape_xml_text(s: str) -> str:
    return html.escape(s, quote=False)


def wrap_xml_tag(tag: str, inner_escaped: str) -> str:
    t = inner_escaped.strip()
    if not t:
        return f"<{tag}></{tag}>"
    return f"<{tag}>\n{t}\n</{tag}>"


def wrap_after_placeholders(tag: str, raw: str, *, char_name: str, user_name: str) -> str:
    text = replace_placeholders_in_text(raw.strip(), char_name=char_name, user_name=user_name)
    return wrap_xml_tag(tag, escape_xml_text(text))


def wrap_user_name(*, raw: str, char_name: str, user_name: str) -> str:
    return wrap_after_placeholders("UserName", raw, char_name=char_name, user_name=user_name)


def wrap_char_name(*, raw: str) -> str:
    return wrap_xml_tag("CharName", escape_xml_text(raw.strip()))


def wrap_group_roster(*, lines: list[str], char_name: str, user_name: str) -> str:
    block = "\n".join(lines)
    text = replace_placeholders_in_text(block, char_name=char_name, user_name=user_name)
    return wrap_xml_tag("GroupRoster", escape_xml_text(text))


def wrap_acting_as(*, raw: str, char_name: str, user_name: str) -> str:
    return wrap_after_placeholders("ActingAs", raw, char_name=char_name, user_name=user_name)


def wrap_interject_hint() -> str:
    return wrap_xml_tag("InterjectHint", escape_xml_text("请根据当前对话内容进行回复（这是一次额外的插话机会）。"))
