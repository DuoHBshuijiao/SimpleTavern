"""T-804: LLM protocol kernel registry + OpenAI-compatible adapter surface."""

from __future__ import annotations

import pytest

from app.errors import AppError
from app.llm.registry import get_adapter, registered_protocols, reset_adapter_registry_for_tests
from app.llm.types import (
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    OPENAI_COMPATIBLE_PROVIDER,
    GenerationConfig,
    Usage,
)
from app.llm.providers.openai_compatible_chat import OpenAICompatibleChatAdapter, decode_usage


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_adapter_registry_for_tests()
    yield
    reset_adapter_registry_for_tests()


def test_registry_resolves_openai_compatible_chat() -> None:
    adapter = get_adapter(OPENAI_COMPATIBLE_CHAT_PROTOCOL)
    assert isinstance(adapter, OpenAICompatibleChatAdapter)
    assert adapter.provider == OPENAI_COMPATIBLE_PROVIDER
    assert adapter.protocol == OPENAI_COMPATIBLE_CHAT_PROTOCOL
    assert OPENAI_COMPATIBLE_CHAT_PROTOCOL in registered_protocols()


def test_registry_unknown_protocol_fast_fails() -> None:
    with pytest.raises(AppError) as exc_info:
        get_adapter("anthropic_messages")
    err = exc_info.value
    assert err.code == "provider_capability_unsupported"
    assert err.protocol == "anthropic_messages"


def test_registry_empty_protocol_is_config_missing() -> None:
    with pytest.raises(AppError) as exc_info:
        get_adapter("  ")
    assert exc_info.value.code == "config_missing"


def test_adapter_validate_config_requires_base_url() -> None:
    adapter = get_adapter(OPENAI_COMPATIBLE_CHAT_PROTOCOL)
    with pytest.raises(AppError) as exc_info:
        adapter.validate_config(base_url="", api_key="k")
    assert exc_info.value.code == "config_missing"


def test_adapter_build_request_shape() -> None:
    adapter = get_adapter(OPENAI_COMPATIBLE_CHAT_PROTOCOL)
    req = adapter.build_request(
        base_url="https://api.example.com/v1",
        api_key="secret",
        messages=[{"role": "user", "content": "hi"}],
        config=GenerationConfig(model="m1", temperature=0.2, max_tokens=16, stream=True),
    )
    assert req.method == "POST"
    assert req.url.endswith("/chat/completions")
    assert req.json_body is not None
    assert req.json_body["model"] == "m1"
    assert req.json_body["stream"] is True
    assert req.json_body["max_tokens"] == 16
    assert req.json_body["max_completion_tokens"] == 16
    assert "Authorization" in req.headers


def test_decode_usage_normalizes_openai_shape() -> None:
    usage = decode_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
    )
    assert isinstance(usage, Usage)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 4
    assert usage.total_tokens == 14
    assert usage.reasoning_tokens == 2
    assert decode_usage(None) is None
    assert decode_usage({}) is None
