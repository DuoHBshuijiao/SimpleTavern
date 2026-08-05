"""LLM protocol kernel shared types (T-804/T-805)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProtocolId = Literal[
    "openai_compatible_chat",
    "openai_responses",
    "anthropic_messages",
    "gemini_generate_content",
]

OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
OPENAI_COMPATIBLE_CHAT_PROTOCOL: ProtocolId = "openai_compatible_chat"
OPENAI_RESPONSES_PROTOCOL: ProtocolId = "openai_responses"
ANTHROPIC_MESSAGES_PROTOCOL: ProtocolId = "anthropic_messages"
GEMINI_GENERATE_CONTENT_PROTOCOL: ProtocolId = "gemini_generate_content"

_KNOWN_PROTOCOLS: frozenset[str] = frozenset(
    {
        OPENAI_COMPATIBLE_CHAT_PROTOCOL,
        OPENAI_RESPONSES_PROTOCOL,
        ANTHROPIC_MESSAGES_PROTOCOL,
        GEMINI_GENERATE_CONTENT_PROTOCOL,
    }
)

_PROTOCOL_PROVIDERS: dict[str, str] = {
    OPENAI_COMPATIBLE_CHAT_PROTOCOL: OPENAI_COMPATIBLE_PROVIDER,
    OPENAI_RESPONSES_PROTOCOL: "openai",
    ANTHROPIC_MESSAGES_PROTOCOL: "anthropic",
    GEMINI_GENERATE_CONTENT_PROTOCOL: "gemini",
}


def normalize_protocol_id(raw: str | None, *, default: ProtocolId = OPENAI_COMPATIBLE_CHAT_PROTOCOL) -> str:
    """Normalize persisted protocol; empty/unknown non-empty values fall back to default only when empty.

    Unknown non-empty ids are returned as-is so registry can fast-fail.
    """
    key = str(raw or "").strip()
    if not key:
        return default
    return key


def provider_id_for_protocol(protocol: str | None) -> str:
    key = normalize_protocol_id(protocol)
    return _PROTOCOL_PROVIDERS.get(key, OPENAI_COMPATIBLE_PROVIDER)


def is_known_protocol_id(protocol: str | None) -> bool:
    return normalize_protocol_id(protocol) in _KNOWN_PROTOCOLS


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
    """Normalized usage placeholder (T-807 will persist). Terminal-state values only."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
