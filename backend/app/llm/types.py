"""LLM protocol kernel shared types (T-804).

Keep thin for batch 1: wire request + generation config + usage placeholder.
Full Canonical Message / ledger belong to later tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProtocolId = Literal["openai_compatible_chat"]

OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
OPENAI_COMPATIBLE_CHAT_PROTOCOL: ProtocolId = "openai_compatible_chat"


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    extra_body: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    stream: bool = False


@dataclass(frozen=True)
class WireRequest:
    """Upstream HTTP request assembled by an adapter."""

    method: str
    url: str
    headers: dict[str, str]
    json_body: dict[str, Any] | None = None


@dataclass(frozen=True)
class Usage:
    """Normalized usage placeholder (T-807 will persist)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
