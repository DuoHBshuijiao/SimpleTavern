"""T-806-6A: Anthropic prompt cache enum helpers."""

from app.llm.types import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    attach_protocol_extra_body,
    normalize_anthropic_prompt_cache,
)


def test_normalize_anthropic_prompt_cache_enum_and_bool() -> None:
    assert normalize_anthropic_prompt_cache(None) == "off"
    assert normalize_anthropic_prompt_cache("") == "off"
    assert normalize_anthropic_prompt_cache("5m") == "5m"
    assert normalize_anthropic_prompt_cache("1H") == "1h"
    assert normalize_anthropic_prompt_cache(True) == "5m"
    assert normalize_anthropic_prompt_cache(False) == "off"
    assert normalize_anthropic_prompt_cache("nope") == "off"


def test_attach_protocol_extra_body_only_for_anthropic() -> None:
    body = attach_protocol_extra_body(
        {"thinking": {"type": "enabled"}},
        protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        anthropic_prompt_cache="1h",
    )
    assert body["anthropic_prompt_cache"] == "1h"
    assert body["thinking"] == {"type": "enabled"}

    stripped = attach_protocol_extra_body(
        body,
        protocol=OPENAI_COMPATIBLE_CHAT_PROTOCOL,
        anthropic_prompt_cache="1h",
    )
    assert "anthropic_prompt_cache" not in stripped
    assert stripped["thinking"] == {"type": "enabled"}

    off = attach_protocol_extra_body(
        None,
        protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        anthropic_prompt_cache="off",
    )
    assert "anthropic_prompt_cache" not in off
