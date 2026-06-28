"""Resolve LLM API credentials from global settings and API presets.

The runtime used to resolve credentials independently in generate,
assistant and MVU paths.  This module keeps the selection contract in one
place so invalid presets fail early instead of silently using a different
endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import ApiPreset, Settings


@dataclass(frozen=True)
class LlmPresetCredentials:
    base_url: str
    api_key: str
    preset_id: str | None
    source: str


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


def _credential_from_preset(preset: ApiPreset, *, source: str) -> LlmPresetCredentials:
    if not is_llm_api_preset(preset):
        raise LlmPresetResolveError(
            "PRESET_NOT_LLM",
            f"API 预设「{preset.name}」是 TTS 预设，不能用于文本生成。",
        )
    if not (preset.baseUrl or "").strip():
        raise LlmPresetResolveError("MISSING_BASE_URL", f"API 预设「{preset.name}」缺少 Base URL。")
    if not (preset.apiKey or "").strip():
        raise LlmPresetResolveError("MISSING_API_KEY", f"API 预设「{preset.name}」缺少 API Key。")
    return LlmPresetCredentials(
        base_url=preset.baseUrl.strip(),
        api_key=preset.apiKey.strip(),
        preset_id=preset.id,
        source=source,
    )


def _credential_from_global(settings: Settings) -> LlmPresetCredentials | None:
    base_url = (settings.llm.baseUrl or "").strip()
    api_key = (settings.llm.apiKey or "").strip()
    if not _has_credentials(base_url, api_key):
        return None
    return LlmPresetCredentials(base_url=base_url, api_key=api_key, preset_id=None, source="global")


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
