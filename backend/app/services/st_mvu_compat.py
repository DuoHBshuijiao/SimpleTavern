"""SillyTavern MVU import compatibility helpers.

本模块只分析 ST 原始卡片并返回结构化结果；不进行任何磁盘写入。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.regex_compat import compile_user_regex
from app.schemas import ChatContentRegexRule, StatusTableDef

Analyzer = Callable[[dict[str, Any]], dict[str, Any]]

_MAX_SNIPPET_CHARS = 700
_MAX_ITEMS = 12
_MAX_REGEX_RULES = 100
_HTML_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_UI_TOKEN_RE = re.compile(r"<\s*(script|style|button|input|select|textarea|template|iframe|svg|canvas)\b|on\w+\s*=", re.I)
_MVU_KEYWORDS = (
    "mvu",
    "tavern_helper",
    "状态",
    "变量",
    "状态栏",
    "好感",
    "位置",
    "装备",
    "status",
    "variable",
)


def _merged_st_card_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    merged = dict(raw)
    merged.update(data)
    return merged


def _clean_snippet(value: Any, *, limit: int = _MAX_SNIPPET_CHARS) -> str:
    text = value if isinstance(value, str) else str(value or "")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = _HTML_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def _extension_value(merged: dict[str, Any], key: str) -> Any:
    extensions = merged.get("extensions")
    if isinstance(extensions, dict) and key in extensions:
        return extensions.get(key)
    return merged.get(key)


def _summarize_tavern_helper(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return {
            "keys": sorted(str(k) for k in raw.keys())[:_MAX_ITEMS],
            "summary": _clean_snippet(raw, limit=500),
        }
    return {"keys": [], "summary": _clean_snippet(raw, limit=500)}


def _summarize_regex_scripts(raw: Any) -> list[dict[str, Any]]:
    scripts: list[Any]
    if isinstance(raw, list):
        scripts = raw
    elif isinstance(raw, dict):
        scripts = list(raw.values())
    elif raw:
        scripts = [raw]
    else:
        scripts = []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(scripts[:_MAX_ITEMS]):
        if isinstance(item, dict):
            name = _clean_snippet(item.get("scriptName") or item.get("name") or item.get("id") or f"regex script {idx + 1}", limit=100)
            pattern = _clean_snippet(item.get("findRegex") or item.get("pattern") or item.get("regex") or "", limit=180)
            replace = _clean_snippet(item.get("replaceString") or item.get("replacement") or "", limit=180)
        else:
            name = f"regex script {idx + 1}"
            pattern = _clean_snippet(item, limit=180)
            replace = ""
        out.append({"name": name, "patternSummary": pattern, "replacementSummary": replace})
    return out


def _raw_regex_scripts(raw: Any) -> list[dict[str, Any]]:
    scripts: list[Any]
    if isinstance(raw, list):
        scripts = raw
    elif isinstance(raw, dict):
        scripts = list(raw.values())
    elif raw:
        scripts = [raw]
    else:
        scripts = []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(scripts[:_MAX_REGEX_RULES]):
        if isinstance(item, dict):
            out.append(dict(item))
        else:
            out.append({"scriptName": f"regex script {idx + 1}", "findRegex": str(item or "")})
    return out


def _book_candidates(character_book: Any) -> list[dict[str, Any]]:
    if not isinstance(character_book, dict):
        return []
    entries = character_book.get("entries")
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        title = _clean_snippet(entry.get("comment") or entry.get("name") or f"条目 {idx + 1}", limit=120)
        keys = entry.get("keys") if isinstance(entry.get("keys"), list) else []
        key_list = [_clean_snippet(k, limit=80) for k in keys if str(k or "").strip()][:_MAX_ITEMS]
        content = _clean_snippet(entry.get("content") or "")
        probe = "\n".join([title, " ".join(key_list), content]).lower()
        if not any(keyword.lower() in probe for keyword in _MVU_KEYWORDS):
            continue
        out.append({
            "index": idx,
            "title": title,
            "enabled": bool(entry.get("enabled", True)),
            "keys": key_list,
            "contentSummary": content,
        })
    return out[:_MAX_ITEMS]


def _greeting_snippets(merged: dict[str, Any]) -> list[str]:
    raw_items: list[Any] = []
    if merged.get("first_mes"):
        raw_items.append(merged.get("first_mes"))
    alternates = merged.get("alternate_greetings")
    if isinstance(alternates, list):
        raw_items.extend(alternates[:4])
    snippets: list[str] = []
    for item in raw_items:
        text = item.get("text") if isinstance(item, dict) else item
        cleaned = _clean_snippet(text, limit=400)
        if cleaned:
            snippets.append(cleaned)
    return snippets[:5]


def extract_st_mvu_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """提取供 MVU 兼容 Agent/分析器使用的瘦身 payload。"""
    merged = _merged_st_card_data(raw)
    tavern_helper = _summarize_tavern_helper(_extension_value(merged, "tavern_helper"))
    regex_scripts = _summarize_regex_scripts(_extension_value(merged, "regex_scripts"))
    character_book = merged.get("character_book")
    return {
        "characterName": _clean_snippet(merged.get("name") or "新角色", limit=120),
        "tavernHelper": tavern_helper,
        "regexScripts": regex_scripts,
        "characterBookCandidates": _book_candidates(character_book),
        "greetingSnippets": _greeting_snippets(merged),
    }


def _default_directive_from_payload(payload: dict[str, Any]) -> str:
    parts = [
        "你是 SimpleTavern 的 MVU 状态维护 Agent。",
        "本角色来自 SillyTavern MVU 角色卡导入；请根据最近对话中明确出现的状态变化维护状态表。",
        "只在文本有直接依据时更新状态，不要编造未出现的数值。",
    ]
    candidates = payload.get("characterBookCandidates") or []
    if candidates:
        parts.append("优先参考以下 ST 世界书候选条目的状态更新意图：")
        for item in candidates[:6]:
            title = str(item.get("title") or "未命名条目")
            summary = str(item.get("contentSummary") or "")
            parts.append(f"- {title}: {summary[:260]}")
    regex_scripts = payload.get("regexScripts") or []
    if regex_scripts:
        parts.append("检测到 ST regex_scripts；当前 L4 不生成正文正则规则，仅将其作为指令模式线索。")
        for item in regex_scripts[:4]:
            parts.append(f"- {item.get('name') or 'regex script'}")
    return "\n".join(parts).strip()


def _default_initial_tables(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("characterBookCandidates") or []
    rows: list[dict[str, Any]] = []
    for item in candidates[:8]:
        title = str(item.get("title") or "").strip()
        if title:
            rows.append({"field": title, "cells": {"当前值": "待观察"}})
    if not rows and (payload.get("tavernHelper") or payload.get("regexScripts")):
        rows.append({"field": "MVU 状态", "cells": {"当前值": "待观察"}})
    if not rows:
        return []
    return [{"name": "ST MVU 初始状态", "columns": ["当前值"], "rows": rows}]


def validate_st_mvu_compat_result(result: dict[str, Any]) -> dict[str, Any]:
    """校验并归一化兼容分析结果。"""
    directive = str(result.get("directive") or "").strip()
    raw_tables = result.get("initialStateTables")
    tables: list[dict[str, Any]] = []
    if isinstance(raw_tables, list):
        tables = [StatusTableDef.model_validate(item).model_dump(mode="json") for item in raw_tables]
    raw_warnings = result.get("warnings")
    warnings = [str(w).strip() for w in raw_warnings if str(w).strip()] if isinstance(raw_warnings, list) else []
    raw_marks = result.get("worldbookMarks")
    marks = raw_marks if isinstance(raw_marks, list) else []
    confidence_raw = result.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except Exception:
        confidence = 0.0
    applied = bool(result.get("applied", bool(directive or tables)))
    return {
        "mode": "directive",
        "applied": applied,
        "directive": directive,
        "initialStateTables": tables,
        "worldbookMarks": marks,
        "warnings": warnings,
        "confidence": confidence,
        "summary": str(result.get("summary") or "").strip(),
    }


def _regex_script_name(item: dict[str, Any], idx: int) -> str:
    return _clean_snippet(
        item.get("scriptName") or item.get("name") or item.get("id") or f"regex script {idx + 1}",
        limit=100,
    )


def _regex_script_pattern(item: dict[str, Any]) -> str:
    for key in ("findRegex", "pattern", "regex"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _regex_script_replacement(item: dict[str, Any]) -> tuple[bool, str]:
    for key in ("replaceString", "replacement"):
        if key in item:
            return True, str(item.get(key) or "")
    return False, ""


def _is_update_variable_pattern(pattern: str) -> bool:
    text = (pattern or "").strip()
    return "UpdateVariable" in text and "</UpdateVariable>" in text


def _looks_like_large_html_ui(*values: str) -> bool:
    text = "\n".join(v for v in values if v)
    if not text:
        return False
    if _UI_TOKEN_RE.search(text):
        return True
    return len(text) > 1200 and bool(_HTML_RE.search(text))


def _validated_regex_rule(rule: dict[str, Any]) -> dict[str, Any]:
    compile_user_regex(str(rule.get("pattern") or ""))
    return ChatContentRegexRule.model_validate(rule).model_dump(mode="json")


def validate_st_mvu_regex_compat_result(result: dict[str, Any]) -> dict[str, Any]:
    """校验并归一化 regex 兼容分析结果。"""
    raw_rules = result.get("regexRules")
    rules: list[dict[str, Any]] = []
    warnings: list[str] = []
    if isinstance(raw_rules, list):
        for idx, item in enumerate(raw_rules[:_MAX_REGEX_RULES]):
            if not isinstance(item, dict):
                warnings.append(f"regex 规则 {idx + 1} 不是对象，已跳过。")
                continue
            try:
                rules.append(_validated_regex_rule(item))
            except Exception as e:
                detail = str(e).strip() or type(e).__name__
                warnings.append(f"regex 规则 {idx + 1} 校验失败，已跳过（{detail}）")
    raw_warnings = result.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(w).strip() for w in raw_warnings if str(w).strip())
    raw_marks = result.get("worldbookMarks")
    marks = raw_marks if isinstance(raw_marks, list) else []
    confidence_raw = result.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except Exception:
        confidence = 0.0
    return {
        "mode": "regex",
        "applied": bool(result.get("applied", bool(rules))) and bool(rules),
        "regexRules": rules,
        "worldbookMarks": marks,
        "warnings": warnings,
        "confidence": confidence,
        "summary": str(result.get("summary") or (f"生成 regex 兼容规则 {len(rules)} 条。" if rules else "未生成 regex 兼容规则。")).strip(),
    }


def build_regex_compat_result(raw: dict[str, Any], analyzer: Analyzer | None = None) -> dict[str, Any]:
    """生成 regex 兼容结果；仅转换 SimpleTavern 可表达的 ST regex_scripts。"""
    merged = _merged_st_card_data(raw)
    payload = extract_st_mvu_payload(raw)
    if analyzer is not None:
        return validate_st_mvu_regex_compat_result(analyzer(payload))

    scripts = _raw_regex_scripts(_extension_value(merged, "regex_scripts"))
    rules: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, item in enumerate(scripts[:_MAX_REGEX_RULES]):
        name = _regex_script_name(item, idx)
        pattern = _regex_script_pattern(item)
        has_replacement, replacement = _regex_script_replacement(item)
        if not pattern:
            warnings.append(f"{name} 缺少 findRegex，已跳过。")
            continue
        if _looks_like_large_html_ui(pattern, replacement):
            warnings.append(f"{name} 包含大型 HTML/UI 或事件逻辑，SimpleTavern regex 不可表达，已跳过。")
            continue
        if _is_update_variable_pattern(pattern):
            rule = {
                "name": f"ST MVU：{name}",
                "enabled": True,
                "order": len(rules),
                "pattern": pattern,
                "action": "remove",
                "matchMode": "global",
            }
        elif has_replacement:
            rule = {
                "name": f"ST regex：{name}",
                "enabled": True,
                "order": len(rules),
                "pattern": pattern,
                "action": "replace",
                "replacement": replacement,
                "matchMode": "global",
            }
        else:
            warnings.append(f"{name} 不是隐藏 UpdateVariable 规则且缺少 replaceString，已跳过。")
            continue
        try:
            rules.append(_validated_regex_rule(rule))
        except Exception as e:
            detail = str(e).strip() or type(e).__name__
            warnings.append(f"{name} 无法编译为 SimpleTavern regex，已跳过（{detail}）")

    marks = [
        {"title": item.get("title"), "reason": "ST 世界书 MVU 候选"}
        for item in (payload.get("characterBookCandidates") or [])[:_MAX_ITEMS]
    ]
    if not scripts:
        warnings.append("未检测到 ST regex_scripts，未生成 regex 兼容规则。")
    return validate_st_mvu_regex_compat_result({
        "regexRules": rules,
        "worldbookMarks": marks,
        "warnings": warnings,
        "confidence": 0.75 if rules else 0.25,
        "summary": f"生成 regex 兼容规则 {len(rules)} 条。" if rules else "未生成 regex 兼容规则。",
    })


def build_directive_compat_result(payload: dict[str, Any], analyzer: Analyzer | None = None) -> dict[str, Any]:
    """生成 directive 兼容结果；analyzer 可替换为真实 Agent 或测试 fake。"""
    if analyzer is not None:
        return validate_st_mvu_compat_result(analyzer(payload))
    tables = _default_initial_tables(payload)
    marks = [
        {"title": item.get("title"), "reason": "ST 世界书 MVU 候选"}
        for item in (payload.get("characterBookCandidates") or [])[:_MAX_ITEMS]
    ]
    warnings = ["L4 暂不生成 regex 模式规则；已保留原 SillyTavern 世界书。"]
    if not tables:
        warnings.append("未提取到明确初始状态表，已仅生成指令模式提示词。")
    return validate_st_mvu_compat_result({
        "directive": _default_directive_from_payload(payload),
        "initialStateTables": tables,
        "worldbookMarks": marks,
        "warnings": warnings,
        "confidence": 0.55 if tables else 0.35,
        "summary": f"生成 directive 指令，初始状态表 {len(tables)} 张。",
    })


def run_st_mvu_compat_agent(raw: dict[str, Any], analyzer: Analyzer | None = None) -> dict[str, Any]:
    """构建 ST MVU payload 并运行兼容分析。"""
    payload = extract_st_mvu_payload(raw)
    return build_directive_compat_result(payload, analyzer=analyzer)


def run_st_mvu_regex_compat_agent(raw: dict[str, Any], analyzer: Analyzer | None = None) -> dict[str, Any]:
    """构建 ST MVU payload 并运行 regex 兼容分析。"""
    return build_regex_compat_result(raw, analyzer=analyzer)
