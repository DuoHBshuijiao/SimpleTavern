"""Resolve LLM API credentials from global settings and API presets.

The runtime used to resolve credentials independently in generate,
assistant and MVU paths.  This module keeps the selection contract in one
place so invalid presets fail early instead of silently using a different
endpoint.

T-820/T-821 起额外携带：供应商目录 id / 占位符参数 / 鉴权风格 / 统一 promptCache。
``protocol`` 可能为 ``auto``（T-822），必须经 ``llm.resolution`` 解析后再进 registry。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.types import (
    ANTHROPIC_PROMPT_CACHE_OFF,
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    normalize_anthropic_prompt_cache,
    normalize_auth_style,
    normalize_protocol_id,
)
from app.schemas import ApiPreset, PromptCacheConfig, Settings


@dataclass(frozen=True)
class LlmPresetCredentials:
    base_url: str
    api_key: str
    preset_id: str | None
    source: str
    protocol: str = OPENAI_COMPATIBLE_CHAT_PROTOCOL
    anthropic_prompt_cache: str = ANTHROPIC_PROMPT_CACHE_OFF
    prompt_cache: PromptCacheConfig = field(default_factory=lambda: PromptCacheConfig(mode="off"))
    provider_id: str | None = None
    provider_params: dict[str, str] = field(default_factory=dict)
    auth_style: str | None = None
    preset_name: str | None = None
    # 预设 / 全局连接级「回传思考内容」开关；最终生效值还要看 settings.reasoningEchoBack（见 llm.resolution）
    echo_reasoning: bool = True


class LlmPresetResolveError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def is_llm_api_preset(preset: ApiPreset) -> bool:
    """Return True when an API preset is usable for LLM calls."""
    kind = (preset.presetKind or "").strip().lower()
    return kind not in {"tts", "minimax"}


def _has_credentials(base_url: str | None, api_key: str | None) -> bool:
    return bool((base_url or "").strip()) and bool((api_key or "").strip())


def _prompt_cache_of(obj: Any) -> PromptCacheConfig:
    raw = getattr(obj, "promptCache", None)
    if isinstance(raw, PromptCacheConfig):
        return raw
    if isinstance(raw, dict):
        return PromptCacheConfig.model_validate(raw)
    from app.schemas import prompt_cache_from_legacy

    return prompt_cache_from_legacy(getattr(obj, "anthropicPromptCache", None))


def _credential_from_preset(preset: ApiPreset, *, source: str) -> LlmPresetCredentials:
    if not is_llm_api_preset(preset):
        raise LlmPresetResolveError(
            "PRESET_NOT_LLM",
            f"API 预设「{preset.name}」是 TTS 预设，不能用于文本生成。",
        )
    if not (preset.baseUrl or "").strip():
        raise LlmPresetResolveError("MISSING_BASE_URL", f"API 预设「{preset.name}」缺少 Base URL。")
    requires_oauth = str(getattr(preset, "authStyle", "") or "").startswith("oauth")
    if not (preset.apiKey or "").strip() and not requires_oauth:
        raise LlmPresetResolveError("MISSING_API_KEY", f"API 预设「{preset.name}」缺少 API Key。")
    return LlmPresetCredentials(
        base_url=preset.baseUrl.strip(),
        api_key=(preset.apiKey or "").strip(),
        preset_id=preset.id,
        source=source,
        protocol=normalize_protocol_id(getattr(preset, "protocol", None)),
        anthropic_prompt_cache=normalize_anthropic_prompt_cache(
            getattr(preset, "anthropicPromptCache", None)
        ),
        prompt_cache=_prompt_cache_of(preset),
        provider_id=(getattr(preset, "providerId", None) or None),
        provider_params=dict(getattr(preset, "providerParams", None) or {}),
        auth_style=normalize_auth_style(getattr(preset, "authStyle", None)),
        preset_name=preset.name,
        echo_reasoning=bool(getattr(preset, "echoReasoning", True)),
    )


def _credential_from_global(settings: Settings) -> LlmPresetCredentials | None:
    base_url = (settings.llm.baseUrl or "").strip()
    api_key = (settings.llm.apiKey or "").strip()
    if not _has_credentials(base_url, api_key):
        return None
    return LlmPresetCredentials(
        base_url=base_url,
        api_key=api_key,
        preset_id=None,
        source="global",
        protocol=normalize_protocol_id(getattr(settings.llm, "protocol", None)),
        anthropic_prompt_cache=normalize_anthropic_prompt_cache(
            getattr(settings.llm, "anthropicPromptCache", None)
        ),
        prompt_cache=_prompt_cache_of(settings.llm),
        provider_id=(getattr(settings.llm, "providerId", None) or None),
        provider_params=dict(getattr(settings.llm, "providerParams", None) or {}),
        auth_style=normalize_auth_style(getattr(settings.llm, "authStyle", None)),
        preset_name=None,
        echo_reasoning=bool(getattr(settings.llm, "echoReasoning", True)),
    )


def resolve_llm_preset_credentials(
    settings: Settings,
    *,
    model: str | None = None,
    explicit_preset_id: str | None = None,
) -> LlmPresetCredentials:
    """Resolve LLM credentials with a deterministic fast-fail contract.

    Priority:
    1. explicit preset id;
    2. LLM preset whose model list contains the selected model;
    3. global LLM credentials when both Base URL and API Key are configured;
    4. first LLM preset that has complete credentials.
    """
    presets = list(settings.apiPresets or [])
    preset_id = (explicit_preset_id or "").strip()
    if preset_id:
        preset = next((p for p in presets if p.id == preset_id), None)
        if preset is None:
            raise LlmPresetResolveError("PRESET_NOT_FOUND", f"找不到 API 预设：{preset_id}")
        return _credential_from_preset(preset, source="explicit")

    selected_model = (model or "").strip()
    if selected_model:
        for preset in presets:
            if not is_llm_api_preset(preset):
                continue
            if selected_model in [m.strip() for m in (preset.models or [])]:
                return _credential_from_preset(preset, source="model")

    global_credentials = _credential_from_global(settings)
    if global_credentials is not None:
        return global_credentials

    for preset in presets:
        if not is_llm_api_preset(preset):
            continue
        if _has_credentials(preset.baseUrl, preset.apiKey):
            return _credential_from_preset(preset, source="first_preset")

    raise LlmPresetResolveError(
        "MISSING_LLM_CREDENTIALS",
        "未配置可用的 LLM API 凭证。请填写全局 Base URL/API Key，或配置至少一个完整的 LLM API 预设。",
    )
