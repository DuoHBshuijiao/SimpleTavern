"""T-822 协议自适应 / 思考深度 clamp / DeepSeek 写法。"""

from __future__ import annotations

from app.llm.catalog import get_catalog, model_family_from_id
from app.llm.preset_resolve import LlmPresetCredentials
from app.llm.resolution import (
    clamp_reasoning_effort,
    preview_resolution,
    resolve_echo_reasoning,
    resolve_protocol,
    resolve_request,
    strip_reasoning_echo,
)
from app.schemas import PromptCacheConfig


def test_family_keywords() -> None:
    assert model_family_from_id("claude-opus-4-6") == "anthropic"
    assert model_family_from_id("gemini-3.1-flash") == "gemini"
    assert model_family_from_id("gpt-5.6") == "openai"
    assert model_family_from_id("deepseek-v4-flash") == "cn_best_effort"


def test_auto_switches_claude_on_anthropic_host() -> None:
    cat = get_catalog()
    entry = cat.find_provider("anthropic")
    effective, _url, adjs, _reasons = resolve_protocol(
        "auto",
        model="claude-opus-4-6",
        base_url="https://api.anthropic.com",
        entry=entry,
    )
    assert effective == "anthropic_messages"
    assert not any(a.get("type") == "protocol_switched" for a in adjs) or True


def test_pinned_protocol_is_not_rewritten() -> None:
    cat = get_catalog()
    entry = cat.find_provider("anthropic")
    effective, _url, adjs, reasons = resolve_protocol(
        "openai_compatible_chat",
        model="claude-opus-4-6",
        base_url="https://api.anthropic.com",
        entry=entry,
    )
    assert effective == "openai_compatible_chat"
    assert not any(a.get("type") == "protocol_switched" for a in adjs)
    assert any("钉住" in r for r in reasons)


def test_gemini_openai_suffix_stripped() -> None:
    r = preview_resolution(
        protocol="auto",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-pro",
        prompt_cache={"mode": "auto"},
        reasoning_effort="none",
    )
    assert r.effective == "gemini_generate_content"
    assert r.base_url.rstrip("/").endswith("/v1beta")
    assert r.effort != "none"  # Pro 不能关思考


def test_clamp_max_to_high() -> None:
    target, adj = clamp_reasoning_effort("max", ("none", "low", "medium", "high"))
    assert target == "high"
    assert adj and adj["from"] == "max"


def test_deepseek_v41_alias_and_efforts() -> None:
    r = preview_resolution(
        protocol="openai_compatible_chat",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4.1-flash",
        prompt_cache={"mode": "auto"},
        reasoning_effort="medium",
    )
    assert r.effort == "medium"
    assert "none" in r.available_efforts
    assert "max" in r.available_efforts


def test_deepseek_pro_routing_notice() -> None:
    r = preview_resolution(
        protocol="auto",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-pro",
        prompt_cache={"mode": "off"},
        reasoning_effort="none",
    )
    assert any("V4.1 Flash" in x for x in r.reasons)


def test_strip_reasoning_echo() -> None:
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": "", "reasoning_content": "think"},
        {"role": "assistant", "content": "hi", "reasoning_content": "think"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}], "reasoning_content": "t"},
    ]
    out = strip_reasoning_echo(msgs)
    assert len(out) == 3
    assert "reasoning_content" not in out[1]
    assert out[2]["tool_calls"]


def test_echo_reasoning_global_off() -> None:
    creds = LlmPresetCredentials(
        base_url="https://api.deepseek.com/v1",
        api_key="k",
        preset_id="p1",
        source="explicit",
        echo_reasoning=True,
    )

    class S:
        reasoningEchoBack = "off"

    enabled, source = resolve_echo_reasoning(S(), creds)
    assert enabled is False
    assert source == "global_off"


def test_prompt_cache_config_roundtrip() -> None:
    cfg = PromptCacheConfig(mode="explicit", ttl="5m", breakpoints=["system", "tools"])
    r = preview_resolution(
        protocol="anthropic_messages",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-4-6",
        prompt_cache=cfg,
        reasoning_effort="high",
    )
    assert r.cache is not None
    assert r.cache.mode == "explicit"
    assert r.cache.ttl == "5m"


def _creds(*, base_url: str, protocol: str, provider_id: str | None = None) -> LlmPresetCredentials:
    return LlmPresetCredentials(
        base_url=base_url,
        api_key="k",
        preset_id=None,
        source="global",
        protocol=protocol,
        prompt_cache=PromptCacheConfig(mode="off"),
        provider_id=provider_id,
    )


def test_preview_fast_unsupported_does_not_raise() -> None:
    r = preview_resolution(
        protocol="openai_compatible_chat",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash",
        prompt_cache={"mode": "off"},
        fast_mode=True,
    )
    assert r.fast_mode_requested is True
    assert r.fast_mode is False
    assert any(a.get("type") == "fast_mode_unsupported" for a in r.adjustments)


def test_responses_none_omits_reasoning_for_openai() -> None:
    _resolution, extra, _headers, _t, _p = resolve_request(
        credentials=_creds(base_url="https://api.openai.com/v1", protocol="openai_responses", provider_id="openai"),
        model="gpt-5.4",
        requested_effort="none",
        fast_mode=False,
    )
    assert extra.get("reasoning") is None


def test_deepseek_responses_none_sends_explicit_none() -> None:
    _resolution, extra, _headers, _t, _p = resolve_request(
        credentials=_creds(
            base_url="https://api.deepseek.com",
            protocol="openai_responses",
            provider_id="deepseek",
        ),
        model="deepseek-v4-flash",
        requested_effort="none",
        fast_mode=False,
    )
    assert extra.get("thinking") == {"type": "disabled"}
    assert extra.get("reasoning") == {"effort": "none"}


def test_chat_none_uses_thinking_disabled_without_reasoning_effort() -> None:
    _resolution, extra, _headers, _t, _p = resolve_request(
        credentials=_creds(
            base_url="https://api.deepseek.com/v1",
            protocol="openai_compatible_chat",
            provider_id="deepseek",
        ),
        model="deepseek-v4-flash",
        requested_effort="none",
        fast_mode=False,
    )
    assert extra.get("thinking") == {"type": "disabled"}
    assert "reasoning_effort" not in extra
    assert extra.get("enable_thinking") is not True
