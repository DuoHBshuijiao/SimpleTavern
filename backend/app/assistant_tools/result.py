"""Unified tool result envelope for assistant tools."""

from __future__ import annotations

import json
from typing import Any

# 进入 LLM 上下文的 ToolResult JSON 体积上限（磁盘仍存完整 JSON）
LLM_TOOL_RESULT_MAX_CHARS = 12000
LLM_TOOL_RESULT_DATA_PREVIEW_CHARS = 400

# Stable machine-readable codes (see plan A.3)
OK = "OK"
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
FORBIDDEN = "FORBIDDEN"
CONFLICT = "CONFLICT"
UPSTREAM_VALIDATION = "UPSTREAM_VALIDATION"
INTERNAL = "INTERNAL"
UNKNOWN_TOOL = "UNKNOWN_TOOL"
LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


def ok(data: dict[str, Any] | None = None, *, tool: str) -> dict[str, Any]:
    return {
        "ok": True,
        "code": OK,
        "data": data or {},
        "meta": {"tool": tool, "version": 1},
    }


def err(
    code: str,
    message: str,
    *,
    tool: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "details": details or {},
        "meta": {"tool": tool, "version": 1},
    }


def _looks_like_tool_result(d: dict[str, Any]) -> bool:
    return isinstance(d.get("ok"), bool) and "code" in d


def compact_tool_result_json_for_llm(text: str, *, max_chars: int = LLM_TOOL_RESULT_MAX_CHARS) -> str:
    """
    将 ToolResult JSON 字符串压缩为适合放入模型上下文的体积；非 JSON 或形态不符则硬截断。
    不改变磁盘持久化内容，仅在构建发给上游的 conversation 时使用。
    """
    if text is None:
        return ""
    stripped = text.strip()
    if not stripped:
        return text
    try:
        d = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped if len(stripped) <= max_chars else stripped[: max_chars - 1] + "…"

    if not isinstance(d, dict) or not _looks_like_tool_result(d):
        s = json.dumps(d, ensure_ascii=False) if isinstance(d, dict) else stripped
        return s if len(s) <= max_chars else s[: max_chars - 1] + "…"

    def build(preview_len: int) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": d["ok"],
            "code": d.get("code"),
        }
        if d.get("message") is not None:
            out["message"] = d["message"]
        if isinstance(d.get("meta"), dict):
            out["meta"] = d["meta"]
        data = d.get("data")
        if data is not None:
            ds = json.dumps(data, ensure_ascii=False)
            if len(ds) > preview_len:
                out["data"] = {
                    "_truncated": True,
                    "preview": ds[:preview_len] + "…",
                }
            else:
                out["data"] = data
        return out

    preview_len = LLM_TOOL_RESULT_DATA_PREVIEW_CHARS
    for _ in range(5):
        compact = build(preview_len)
        s = json.dumps(compact, ensure_ascii=False)
        if len(s) <= max_chars:
            return s
        preview_len = max(80, preview_len // 2)

    compact = build(preview_len)
    s = json.dumps(compact, ensure_ascii=False)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def from_legacy_dict(d: dict[str, Any], *, tool: str) -> dict[str, Any]:
    """Map legacy {ok, error} shapes to ToolResult."""
    if d.get("ok") is True:
        data = {k: v for k, v in d.items() if k not in ("ok", "error")}
        return ok(data, tool=tool)
    msg = str(d.get("error") or d.get("message") or "failed")
    code = NOT_FOUND if "not found" in msg.lower() else VALIDATION_ERROR
    if "forbidden" in msg.lower() or "不允许" in msg or "未允许" in msg:
        code = FORBIDDEN
    return err(code, msg, tool=tool)
