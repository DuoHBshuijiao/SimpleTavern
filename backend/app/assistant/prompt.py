"""Load the chat assistant system prompt from AGENT.md."""

from __future__ import annotations

from pathlib import Path

_AGENT_MD = Path(__file__).resolve().parent / "AGENT.md"
_TTS_POST_PROCESS_MD = Path(__file__).resolve().parent / "TTS_POST_Process.md"


def load_agent_system_prompt() -> str:
    """
    Read UTF-8 AGENT.md next to this module. Used as the sole system prompt for the assistant LLM.

    Raises:
        FileNotFoundError: If AGENT.md is missing.
        ValueError: If the file is empty or whitespace-only.
    """
    if not _AGENT_MD.is_file():
        raise FileNotFoundError(f"assistant system prompt file not found: {_AGENT_MD}")
    text = _AGENT_MD.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"assistant system prompt file is empty: {_AGENT_MD}")
    return text


def load_tts_post_process_prompt() -> str:
    """Read UTF-8 TTS_POST_Process.md next to this module."""
    if not _TTS_POST_PROCESS_MD.is_file():
        raise FileNotFoundError(f"tts post process prompt file not found: {_TTS_POST_PROCESS_MD}")
    text = _TTS_POST_PROCESS_MD.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"tts post process prompt file is empty: {_TTS_POST_PROCESS_MD}")
    return text
