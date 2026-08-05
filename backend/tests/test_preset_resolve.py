import pytest

from app.llm.preset_resolve import LlmPresetResolveError, resolve_llm_preset_credentials
from app.schemas import ApiPreset, Settings, SettingsLLM


def _settings(*, presets: list[ApiPreset], global_key: str = "") -> Settings:
    return Settings(
        llm=SettingsLLM(baseUrl="https://global.example", apiKey=global_key, defaultModel="global-model"),
        apiPresets=presets,
    )


def test_explicit_preset_wins() -> None:
    settings = _settings(
        global_key="global-key",
        presets=[
            ApiPreset(id="a", name="A", baseUrl="https://a.example", apiKey="a-key", models=["m"]),
            ApiPreset(id="b", name="B", baseUrl="https://b.example", apiKey="b-key", models=["m"]),
        ],
    )

    credentials = resolve_llm_preset_credentials(settings, model="m", explicit_preset_id="b")

    assert credentials.base_url == "https://b.example"
    assert credentials.api_key == "b-key"
    assert credentials.source == "explicit"


def test_model_match_ignores_tts_presets() -> None:
    settings = _settings(
        presets=[
            ApiPreset(id="tts", name="TTS", baseUrl="http://127.0.0.1:8088", apiKey="tts", models=["m"], presetKind="tts"),
            ApiPreset(id="llm", name="LLM", baseUrl="https://llm.example", apiKey="llm-key", models=["m"]),
        ],
    )

    credentials = resolve_llm_preset_credentials(settings, model="m")

    assert credentials.preset_id == "llm"
    assert credentials.source == "model"


def test_explicit_tts_preset_fails_fast() -> None:
    settings = _settings(
        presets=[ApiPreset(id="tts", name="TTS", baseUrl="http://127.0.0.1:8088", apiKey="tts", presetKind="tts")]
    )

    with pytest.raises(LlmPresetResolveError) as exc:
        resolve_llm_preset_credentials(settings, explicit_preset_id="tts")

    assert exc.value.code == "PRESET_NOT_LLM"


def test_missing_explicit_preset_fails_fast() -> None:
    with pytest.raises(LlmPresetResolveError) as exc:
        resolve_llm_preset_credentials(_settings(presets=[]), explicit_preset_id="missing")

    assert exc.value.code == "PRESET_NOT_FOUND"


def test_uses_first_complete_llm_preset_when_global_is_incomplete() -> None:
    settings = _settings(
        presets=[ApiPreset(id="llm", name="LLM", baseUrl="https://llm.example", apiKey="llm-key", models=[])],
    )

    credentials = resolve_llm_preset_credentials(settings, model="unknown")

    assert credentials.preset_id == "llm"
    assert credentials.source == "first_preset"


def test_no_credentials_fails_fast() -> None:
    with pytest.raises(LlmPresetResolveError) as exc:
        resolve_llm_preset_credentials(_settings(presets=[]))

    assert exc.value.code == "MISSING_LLM_CREDENTIALS"


def test_preset_protocol_is_resolved() -> None:
    settings = _settings(
        presets=[
            ApiPreset(
                id="anth",
                name="Anthropic",
                baseUrl="https://api.anthropic.com",
                apiKey="k",
                models=["claude"],
                protocol="anthropic_messages",
            )
        ],
    )
    credentials = resolve_llm_preset_credentials(settings, model="claude")
    assert credentials.protocol == "anthropic_messages"


def test_missing_protocol_defaults_to_openai_compatible_chat() -> None:
    settings = _settings(
        presets=[ApiPreset(id="llm", name="LLM", baseUrl="https://llm.example", apiKey="k", models=["m"])],
    )
    credentials = resolve_llm_preset_credentials(settings, model="m")
    assert credentials.protocol == "openai_compatible_chat"


def test_global_protocol_is_resolved() -> None:
    settings = Settings(
        llm=SettingsLLM(
            baseUrl="https://global.example",
            apiKey="global-key",
            defaultModel="g",
            protocol="openai_responses",
        ),
        apiPresets=[],
    )
    credentials = resolve_llm_preset_credentials(settings, model="g")
    assert credentials.source == "global"
    assert credentials.protocol == "openai_responses"


def test_anthropic_prompt_cache_from_preset() -> None:
    settings = _settings(
        presets=[
            ApiPreset(
                id="anth",
                name="Anthropic",
                baseUrl="https://api.anthropic.com",
                apiKey="k",
                models=["claude"],
                protocol="anthropic_messages",
                anthropicPromptCache="1h",
            )
        ],
    )
    credentials = resolve_llm_preset_credentials(settings, model="claude")
    assert credentials.anthropic_prompt_cache == "1h"


def test_anthropic_prompt_cache_bool_legacy_migrates() -> None:
    preset = ApiPreset.model_validate(
        {
            "id": "anth",
            "name": "Anthropic",
            "baseUrl": "https://api.anthropic.com",
            "apiKey": "k",
            "models": ["claude"],
            "protocol": "anthropic_messages",
            "anthropicPromptCache": True,
        }
    )
    assert preset.anthropicPromptCache == "5m"
    settings = _settings(presets=[preset])
    credentials = resolve_llm_preset_credentials(settings, model="claude")
    assert credentials.anthropic_prompt_cache == "5m"


def test_anthropic_prompt_cache_defaults_off() -> None:
    settings = _settings(
        presets=[ApiPreset(id="llm", name="LLM", baseUrl="https://llm.example", apiKey="k", models=["m"])],
    )
    credentials = resolve_llm_preset_credentials(settings, model="m")
    assert credentials.anthropic_prompt_cache == "off"

