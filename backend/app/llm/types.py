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

AnthropicPromptCache = Literal["off", "5m", "1h"]
ANTHROPIC_PROMPT_CACHE_OFF: AnthropicPromptCache = "off"
_ANTHROPIC_PROMPT_CACHE_VALUES: frozenset[str] = frozenset({"off", "5m", "1h"})

# T-822：预设可选「自动（按模型识别）」；必须经 resolution 解析成实际协议后才能进 registry。
PROTOCOL_AUTO = "auto"

# T-821/T-824：调用方经 extra_body 传给 runtime 的内部控制块键名；runtime 取出后适配器永远看不到它。
ST_CONTROL_KEY = "__simpletavern__"

_KNOWN_PROTOCOLS: frozenset[str] = frozenset(
    {
        OPENAI_COMPATIBLE_CHAT_PROTOCOL,
        OPENAI_RESPONSES_PROTOCOL,
        ANTHROPIC_MESSAGES_PROTOCOL,
        GEMINI_GENERATE_CONTENT_PROTOCOL,
    }
)

# T-820-A2：鉴权风格
AuthStyle = Literal["bearer", "x-api-key", "api-key", "x-goog-api-key", "query_key", "oauth_device", "oauth_pkce"]
AUTH_STYLE_DEFAULT: AuthStyle = "bearer"
_KNOWN_AUTH_STYLES: frozenset[str] = frozenset(
    {"bearer", "x-api-key", "api-key", "x-goog-api-key", "query_key", "oauth_device", "oauth_pkce"}
)


def normalize_auth_style(raw: Any, *, default: str | None = None) -> str | None:
    """归一化鉴权风格；空值返回 default（None 表示「按协议默认」），未知值原样返回供 fast-fail。"""
    key = str(raw or "").strip().lower().replace("_", "-") if raw is not None else ""
    if not key:
        return default
    if key in {"oauth-device", "oauth-pkce", "query-key"}:
        key = key.replace("-", "_")
    return key


def is_known_auth_style(raw: Any) -> bool:
    return normalize_auth_style(raw, default=AUTH_STYLE_DEFAULT) in _KNOWN_AUTH_STYLES


def auth_headers_for_style(api_key: str, auth_style: str | None) -> dict[str, str]:
    """按鉴权风格生成请求头（T-820-A2）。``query_key`` 不放头，由 ``append_query_key`` 处理。"""
    key = (api_key or "").strip()
    if not key:
        return {}
    style = normalize_auth_style(auth_style, default=AUTH_STYLE_DEFAULT) or AUTH_STYLE_DEFAULT
    if style == "x-api-key":
        return {"x-api-key": key}
    if style == "api-key":
        return {"api-key": key}
    if style == "x-goog-api-key":
        return {"x-goog-api-key": key}
    if style in {"query_key", "oauth_device", "oauth_pkce"}:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _with_query(url: str, updates: dict[str, str]) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in updates.items():
        query.setdefault(key, value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def append_query_key(url: str, api_key: str, auth_style: str | None) -> str:
    """``query_key``：把 key 接到 URL ``?key=``（部分 Gemini / 旧 Google 端点）。"""
    style = normalize_auth_style(auth_style, default=AUTH_STYLE_DEFAULT)
    if style != "query_key":
        return url
    key = (api_key or "").strip()
    if not key:
        return url
    return _with_query(url, {"key": key})


def append_api_version(url: str, provider_params: dict[str, str] | None) -> str:
    """Azure 等：若 ``providerParams`` 带 ``api_version`` / ``api-version``，接到 ``?api-version=``。"""
    if not provider_params:
        return url
    version = (provider_params.get("api_version") or provider_params.get("api-version") or "").strip()
    if not version:
        return url
    return _with_query(url, {"api-version": version})

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
    return _PROTOCOL_PROVIDERS.get(key, "unknown")


def is_known_protocol_id(protocol: str | None) -> bool:
    return normalize_protocol_id(protocol) in _KNOWN_PROTOCOLS


def is_auto_protocol(protocol: str | None) -> bool:
    return str(protocol or "").strip().lower() == PROTOCOL_AUTO


def normalize_anthropic_prompt_cache(raw: Any, *, default: AnthropicPromptCache = ANTHROPIC_PROMPT_CACHE_OFF) -> AnthropicPromptCache:
    """Normalize Anthropic prompt-cache TTL; bool legacy true→5m, false→off."""
    if isinstance(raw, bool):
        return "5m" if raw else "off"
    key = str(raw or "").strip().lower()
    if not key:
        return default
    if key in {"true", "1", "yes", "on", "enabled"}:
        return "5m"
    if key in {"false", "0", "no", "off", "disabled"}:
        return "off"
    if key in _ANTHROPIC_PROMPT_CACHE_VALUES:
        return key  # type: ignore[return-value]
    return default


def attach_protocol_extra_body(
    extra_body: dict[str, Any] | None,
    *,
    protocol: str | None,
    anthropic_prompt_cache: str | None = None,
) -> dict[str, Any]:
    """Merge protocol-specific knobs into extra_body for adapters (T-806).

    T-821 起结构化缓存计划走 ``ST_CONTROL_KEY`` 控制块；本函数保留给旧调用方（TTS 等）与测试。
    """
    out = dict(extra_body or {})
    proto = normalize_protocol_id(protocol)
    cache = normalize_anthropic_prompt_cache(anthropic_prompt_cache)
    if proto == ANTHROPIC_MESSAGES_PROTOCOL and cache != "off":
        out["anthropic_prompt_cache"] = cache
    else:
        out.pop("anthropic_prompt_cache", None)
    return out


def attach_control_block(
    extra_body: dict[str, Any] | None,
    *,
    prompt_cache: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    auth_style: str | None = None,
    protocol_variant: str | None = None,
    provider_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """把结构化控制信息挂到 extra_body（``ST_CONTROL_KEY``），runtime 取出填入 GenerationConfig。"""
    out = dict(extra_body or {})
    block: dict[str, Any] = dict(out.get(ST_CONTROL_KEY) or {})
    if prompt_cache is not None:
        block["prompt_cache"] = prompt_cache
    if extra_headers:
        merged = dict(block.get("extra_headers") or {})
        merged.update(extra_headers)
        block["extra_headers"] = merged
    if auth_style:
        block["auth_style"] = auth_style
    if protocol_variant:
        block["protocol_variant"] = protocol_variant
    if provider_params:
        block["provider_params"] = dict(provider_params)
    if block:
        out[ST_CONTROL_KEY] = block
    return out


def pop_control_block(extra_body: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """从 extra_body 拆出控制块：返回 (剩余 extra_body, 控制块)。"""
    if not extra_body:
        return extra_body, {}
    if ST_CONTROL_KEY not in extra_body:
        return extra_body, {}
    out = dict(extra_body)
    block = out.pop(ST_CONTROL_KEY) or {}
    return (out or None), (block if isinstance(block, dict) else {})


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
    anthropic_prompt_cache: AnthropicPromptCache | None = None
    # T-821：结构化缓存计划（见 llm/prompt_cache.PromptCachePlan.to_dict）
    prompt_cache: dict[str, Any] | None = None
    # T-824：额外请求头（如 anthropic-beta: fast-mode-2026-02-01）
    extra_headers: dict[str, str] | None = None
    # T-820-A2：鉴权风格与协议变体（如 Anthropic 的 bedrock 变体）
    auth_style: str | None = None
    protocol_variant: str | None = None
    provider_params: dict[str, str] | None = None


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
    # T-824：实际服务档位（OpenAI service_tier / Anthropic usage.speed / Gemini x-gemini-service-tier）
    service_tier: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.input_tokens is not None:
            out["inputTokens"] = self.input_tokens
        if self.output_tokens is not None:
            out["outputTokens"] = self.output_tokens
        if self.total_tokens is not None:
            out["totalTokens"] = self.total_tokens
        if self.cache_read_input_tokens is not None:
            out["cacheReadInputTokens"] = self.cache_read_input_tokens
        if self.cache_write_input_tokens is not None:
            out["cacheWriteInputTokens"] = self.cache_write_input_tokens
        if self.reasoning_tokens is not None:
            out["reasoningTokens"] = self.reasoning_tokens
        if self.service_tier:
            out["serviceTier"] = self.service_tier
        return out
