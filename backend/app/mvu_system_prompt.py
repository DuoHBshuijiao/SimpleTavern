"""Load the MVU agent system prompt from MVU_AGENT.md."""

from __future__ import annotations

from pathlib import Path

_MVU_AGENT_MD = Path(__file__).resolve().parent / "MVU_AGENT.md"


def load_mvu_system_prompt() -> str:
    if not _MVU_AGENT_MD.is_file():
        raise FileNotFoundError(f"MVU agent system prompt file not found: {_MVU_AGENT_MD}")
    text = _MVU_AGENT_MD.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"MVU agent system prompt file is empty: {_MVU_AGENT_MD}")
    return text
