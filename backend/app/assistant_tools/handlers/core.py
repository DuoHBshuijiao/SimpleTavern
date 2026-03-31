"""Core assistant tools (time, etc.)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R


def handle_core_get_time(_ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now()
    return R.ok({"time": now.strftime("%Y/%m/%d - %H:%M:%S")}, tool="core_get_time")
