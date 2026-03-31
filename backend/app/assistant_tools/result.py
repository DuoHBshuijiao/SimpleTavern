"""Unified tool result envelope for assistant tools."""

from __future__ import annotations

from typing import Any

# Stable machine-readable codes (see plan A.3)
OK = "OK"
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
FORBIDDEN = "FORBIDDEN"
CONFLICT = "CONFLICT"
UPSTREAM_VALIDATION = "UPSTREAM_VALIDATION"
INTERNAL = "INTERNAL"
UNKNOWN_TOOL = "UNKNOWN_TOOL"


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
