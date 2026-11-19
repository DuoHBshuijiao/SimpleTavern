from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

import regex

from app.regex_compat import compile_timed_user_regex
from app.schemas import ChatContentRegexRule

_RULE_TIMEOUT_SECONDS = 0.15


def normalize_rule_name(name: str | None, pattern: str) -> str:
    raw = (name or "").strip()
    if raw:
        return raw
    return (pattern or "").strip()[:50]


def normalize_replacement_syntax(replacement: str | None) -> str:
    """将 JS 风格 $N 转为 Python re 可识别的 \g<N>。仅支持数值分组，不支持命名分组。"""
    raw = replacement or ""
    if "$" not in raw:
        return raw
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != "$":
            out.append(ch)
            i += 1
            continue
        if i + 1 < n and raw[i + 1] == "$":
            out.append("$")
            i += 2
            continue
        j = i + 1
        if j < n and raw[j].isdigit():
            k = j
            while k < n and raw[k].isdigit():
                k += 1
            out.append(rf"\g<{raw[j:k]}>")
            i = k
            continue
        out.append("$")
        i += 1
    return "".join(out)


@dataclass
class RuleRunResult:
    persisted_text: str
    display_text: str
    extracted_items: list[dict[str, str]]


@dataclass
class ContentRegexApplyResult:
    persisted_text: str
    display_text: str
    extracted_items: list[dict[str, str]]
    errors: list[dict[str, str]]


def _pick_extracted_text(rule: ChatContentRegexRule, match: regex.Match) -> str:
    if (rule.extractSource or "whole_match") == "whole_match":
        return match.group(0) or ""
    group_index = rule.extractGroupIndex if rule.extractGroupIndex is not None else 1
    try:
        return match.group(group_index) or ""
    except (IndexError, KeyError):
        return ""


def _collect_matches(compiled: regex.Pattern, text: str, mode: Literal["global", "first"], timeout: float) -> list[regex.Match]:
    if mode == "first":
        first = compiled.search(text, timeout=timeout, concurrent=True)
        return [first] if first is not None else []
    return list(compiled.finditer(text, timeout=timeout, concurrent=True))


def _apply_one(rule: ChatContentRegexRule, persisted_text: str, display_text: str, timeout: float) -> RuleRunResult:
    pattern = (rule.pattern or "").strip()
    if not pattern:
        return RuleRunResult(
            persisted_text=persisted_text,
            display_text=display_text,
            extracted_items=[],
        )
    deadline = time.monotonic() + timeout
    compiled = compile_timed_user_regex(pattern, re.MULTILINE | re.DOTALL)

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    def substitute(replacement: str, text: str) -> str:
        return compiled.sub(replacement, text, count=count, timeout=remaining(), concurrent=True)
    count = 0 if (rule.matchMode or "global") == "global" else 1
    action = rule.action or "remove"
    next_persisted = persisted_text
    next_display = display_text
    extracted_items: list[dict[str, str]] = []

    if action in ("extract", "extract_and_replace"):
        matches = _collect_matches(compiled, persisted_text, rule.matchMode or "global", remaining())
        for m in matches:
            extracted_text = _pick_extracted_text(rule, m)
            if not extracted_text:
                continue
            extracted_items.append(
                {
                    "ruleId": str(rule.id),
                    "ruleName": normalize_rule_name(rule.name, rule.pattern),
                    "action": action,
                    "value": extracted_text,
                    "matchedText": m.group(0) or "",
                    "start": str(m.start()),
                    "end": str(m.end()),
                }
            )

    if action == "remove":
        next_persisted = substitute("", persisted_text)
        next_display = next_persisted if display_text == persisted_text else substitute("", display_text)
    elif action == "replace":
        replacement = normalize_replacement_syntax(rule.replacement)
        next_persisted = substitute(replacement, persisted_text)
        next_display = next_persisted if display_text == persisted_text else substitute(replacement, display_text)
    elif action == "extract_and_replace":
        replacement = normalize_replacement_syntax(rule.replacement)
        next_display = substitute(replacement, display_text)

    return RuleRunResult(
        persisted_text=next_persisted,
        display_text=next_display,
        extracted_items=extracted_items,
    )


def apply_content_regex_pipeline(
    text: str,
    rules: list[ChatContentRegexRule] | None,
    *,
    timeout_seconds: float = _RULE_TIMEOUT_SECONDS,
) -> ContentRegexApplyResult:
    persisted_working = text
    display_working = text
    extracted_items: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    ordered = sorted(
        [r for r in (rules or []) if r.enabled and (r.pattern or "").strip()],
        key=lambda r: (int(r.order), str(r.id)),
    )
    for rule in ordered:
        try:
            result = _apply_one(rule, persisted_working, display_working, max(0.01, float(timeout_seconds)))
            persisted_working = result.persisted_text
            display_working = result.display_text
            if result.extracted_items:
                extracted_items.extend(result.extracted_items)
        except TimeoutError:
            errors.append(
                {
                    "ruleId": str(rule.id),
                    "ruleName": normalize_rule_name(rule.name, rule.pattern),
                    "errorCode": "REGEX_TIMEOUT",
                    "error": "rule execution timed out",
                    "pattern": rule.pattern or "",
                    "replacement": rule.replacement or "",
                }
            )
        except regex.error as e:
            errors.append(
                {
                    "ruleId": str(rule.id),
                    "ruleName": normalize_rule_name(rule.name, rule.pattern),
                    "errorCode": "REGEX_INVALID",
                    "error": str(e),
                    "pattern": rule.pattern or "",
                    "replacement": rule.replacement or "",
                }
            )
        except Exception as e:
            errors.append(
                {
                    "ruleId": str(rule.id),
                    "ruleName": normalize_rule_name(rule.name, rule.pattern),
                    "errorCode": "REGEX_ERROR",
                    "error": str(e),
                    "pattern": rule.pattern or "",
                    "replacement": rule.replacement or "",
                }
            )
    return ContentRegexApplyResult(
        persisted_text=persisted_working,
        display_text=display_working,
        extracted_items=extracted_items,
        errors=errors,
    )

