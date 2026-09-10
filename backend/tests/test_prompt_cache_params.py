"""T-821 prompt cache 计划与各协议字段。"""

from __future__ import annotations

from app.llm.prompt_cache import (
    MODE_BEST_EFFORT,
    MODE_EXPLICIT,
    MODE_IMPLICIT,
    anthropic_system_blocks,
    build_prompt_cache_plan,
    dashscope_mark_messages,
    openai_chat_cache_fields,
    openai_responses_cache_fields,
    openai_responses_wants_explicit_breakpoint,
)
from app.llm.types import auth_headers_for_style, append_query_key
from app.schemas import prompt_cache_from_legacy


def test_legacy_off_stays_off() -> None:
    cfg = prompt_cache_from_legacy("off")
    assert cfg.mode == "off"


def test_legacy_ttl_becomes_explicit() -> None:
    cfg = prompt_cache_from_legacy("1h")
    assert cfg.mode == "explicit"
    assert cfg.ttl == "1h"


def test_anthropic_explicit_system_blocks() -> None:
    plan = build_prompt_cache_plan(
        {"mode": "explicit", "ttl": "5m", "breakpoints": ["system"]},
        protocol="anthropic_messages",
        requested_protocol="auto",
        base_url="https://api.anthropic.com",
        model="claude-opus-4-6",
        family="anthropic",
        provider_cache_strategy="explicit",
        provider_explicit_markers=False,
        preset_id=None,
        chat_id="c1",
        character_id=None,
    )
    assert plan.mode == MODE_EXPLICIT
    blocks = anthropic_system_blocks("hello", plan)
    assert isinstance(blocks, list)
    assert blocks[0]["cache_control"]["ttl"] == "5m"


def test_openai_gpt56_uses_options() -> None:
    plan = build_prompt_cache_plan(
        {"mode": "explicit", "ttl": "1h", "cacheKey": "global"},
        protocol="openai_responses",
        requested_protocol="auto",
        base_url="https://api.openai.com/v1",
        model="gpt-5.6",
        family="openai",
        provider_cache_strategy="explicit",
        provider_explicit_markers=False,
        preset_id="p",
        chat_id="c1",
        character_id=None,
    )
    fields = openai_responses_cache_fields(plan)
    assert fields["prompt_cache_options"]["ttl"] == "30m"
    assert openai_responses_wants_explicit_breakpoint(plan)


def test_openai_chat_only_official() -> None:
    plan = build_prompt_cache_plan(
        {"mode": "explicit", "cacheKey": "global"},
        protocol="openai_compatible_chat",
        requested_protocol="openai_compatible_chat",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash",
        family="cn_best_effort",
        provider_cache_strategy="best_effort",
        provider_explicit_markers=False,
        preset_id=None,
        chat_id=None,
        character_id=None,
    )
    assert plan.mode == MODE_BEST_EFFORT
    assert openai_chat_cache_fields(plan) == {}


def test_dashscope_markers() -> None:
    plan = build_prompt_cache_plan(
        {"mode": "explicit", "explicitMarkers": True, "breakpoints": ["system", "history_tail"]},
        protocol="openai_compatible_chat",
        requested_protocol="openai_compatible_chat",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3-max",
        family="cn_best_effort",
        provider_cache_strategy="explicit",
        provider_explicit_markers=True,
        preset_id=None,
        chat_id=None,
        character_id=None,
    )
    msgs = dashscope_mark_messages(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
        plan,
    )
    assert isinstance(msgs[0]["content"], list)
    assert msgs[0]["content"][0]["cache_control"]["type"] == "ephemeral"


def test_auth_headers_styles() -> None:
    assert auth_headers_for_style("k", "bearer") == {"Authorization": "Bearer k"}
    assert auth_headers_for_style("k", "api-key") == {"api-key": "k"}
    assert auth_headers_for_style("k", "x-api-key") == {"x-api-key": "k"}
    assert auth_headers_for_style("k", "x-goog-api-key") == {"x-goog-api-key": "k"}
    url = append_query_key("https://example.com/v1beta/models", "k", "query_key")
    assert "key=k" in url
