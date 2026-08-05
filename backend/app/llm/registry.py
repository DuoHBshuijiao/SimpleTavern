"""LLM adapter registry (T-804)."""

from __future__ import annotations

from app.errors import AppError
from app.llm.protocol import ProviderAdapter
from app.llm.types import OPENAI_COMPATIBLE_CHAT_PROTOCOL, ProtocolId, provider_id_for_protocol

_REGISTRY: dict[str, ProviderAdapter] | None = None


def _build_registry() -> dict[str, ProviderAdapter]:
    from app.llm.providers.openai_compatible_chat import OpenAICompatibleChatAdapter

    adapter = OpenAICompatibleChatAdapter()
    return {adapter.protocol: adapter}


def reset_adapter_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None


def registered_protocols() -> list[str]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return sorted(_REGISTRY.keys())


def get_adapter(protocol: str | ProtocolId) -> ProviderAdapter:
    """Resolve adapter by protocol id. Unknown protocol fast-fails (no silent fallback)."""
    global _REGISTRY
    key = str(protocol or "").strip()
    if not key:
        raise AppError(
            code="config_missing",
            message="未指定 LLM 协议",
            source="llm.registry",
            status_code=400,
            suggested_action="在 API 预设中选择协议后重试",
        )
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    adapter = _REGISTRY.get(key)
    if adapter is None:
        known = ", ".join(registered_protocols()) or "(none)"
        raise AppError(
            code="provider_capability_unsupported",
            message="当前版本不支持该 LLM 协议",
            detail=f"protocol={key}; registered={known}",
            source="llm.registry",
            status_code=400,
            suggested_action=f"请使用已支持的协议（当前：{OPENAI_COMPATIBLE_CHAT_PROTOCOL}）",
            provider=provider_id_for_protocol(key),
            protocol=key,
        )
    return adapter
