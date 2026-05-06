"""Resolve MVU Agent model name from global settings (no chat/session override)."""

from __future__ import annotations

from app.schemas import Settings


def resolve_mvu_model_from_settings(settings: Settings) -> str:
    """优先级：settings.mvuModel → llm.defaultModel → llm.modelCandidates 首项。"""
    for candidate in (
        (settings.mvuModel or "").strip(),
        (settings.llm.defaultModel or "").strip(),
        *((c or "").strip() for c in (settings.llm.modelCandidates or [])),
    ):
        if candidate:
            return candidate
    return ""
