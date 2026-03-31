"""Execution context passed to assistant tool handlers."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AssistantSettings


@dataclass
class AssistantToolContext:
    chat_id: str | None
    scope: str | None
    allow_write_memory: bool
    allow_destructive_tools: bool
    assistant_settings: AssistantSettings
