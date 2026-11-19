from __future__ import annotations

from typing import Any


def split_leading_system_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate global instructions from dialogue and instructions placed within it."""
    instructions: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if not turns and message.get("role") == "system" and not message.get("_system_turn"):
            instructions.append(message)
        else:
            turns.append(message)
    return instructions, turns
