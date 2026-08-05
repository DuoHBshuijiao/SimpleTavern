"""T-805-5B: Anthropic Messages adapter (no tools / cache off)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.errors import AppError
from app.llm.providers.anthropic_messages import (
    AnthropicMessagesAdapter,
    _build_payload,
    _convert_messages,
    _messages_url,
    decode_usage,
)
from app.llm.registry import get_adapter, registered_protocols, reset_adapter_registry_for_tests
from app.llm.types import ANTHROPIC_MESSAGES_PROTOCOL, GenerationConfig


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_adapter_registry_for_tests()
    yield
    reset_adapter_registry_for_tests()


def test_registry_resolves_anthropic_messages() -> None:
    adapter = get_adapter(ANTHROPIC_MESSAGES_PROTOCOL)
    assert isinstance(adapter, AnthropicMessagesAdapter)
    assert ANTHROPIC_MESSAGES_PROTOCOL in registered_protocols()


def test_messages_url_normalizes_bare_host() -> None:
    assert _messages_url("api.anthropic.com") == "https://api.anthropic.com/v1/messages"
    assert _messages_url("https://api.anthropic.com/v1/messages") == "https://api.anthropic.com/v1/messages"


def test_convert_messages_extracts_system_and_merges_roles() -> None:
    system, msgs = _convert_messages(
        [
            {"role": "system", "content": "sys-a"},
            {"role": "system", "content": "sys-b"},
            {"role": "user", "content": "u1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a1"},
        ]
    )
    assert system == "sys-a\n\nsys-b"
    assert msgs == [
        {"role": "user", "content": "u1\nu2"},
        {"role": "assistant", "content": "a1"},
    ]


def test_tools_in_config_fast_fail() -> None:
    adapter = AnthropicMessagesAdapter()
    with pytest.raises(AppError) as exc:
        adapter.build_request(
            base_url="https://api.anthropic.com",
            api_key="k",
            messages=[{"role": "user", "content": "hi"}],
            config=GenerationConfig(
                model="claude-sonnet-4-5",
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            ),
        )
    assert exc.value.code == "provider_capability_unsupported"


def test_tool_role_in_messages_fast_fail() -> None:
    with pytest.raises(AppError) as exc:
        _convert_messages(
            [
                {"role": "user", "content": "hi"},
                {"role": "tool", "tool_call_id": "x", "content": "result"},
            ]
        )
    assert exc.value.code == "provider_capability_unsupported"


def test_build_payload_defaults_max_tokens_and_strips_top_level_cache() -> None:
    payload = _build_payload(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
        temperature=0.2,
        top_p=None,
        max_tokens=None,
        extra_body={"cache_control": {"type": "ephemeral"}, "reasoning_effort": "high"},
    )
    assert payload["max_tokens"] == 4096
    assert payload["temperature"] == 0.2
    assert "cache_control" not in payload
    assert "reasoning_effort" not in payload
    assert "system" not in payload


def test_build_payload_applies_system_cache_5m() -> None:
    payload = _build_payload(
        model="claude-sonnet-4-5",
        messages=[
            {"role": "system", "content": "stable-sys"},
            {"role": "user", "content": "hi"},
        ],
        stream=False,
        temperature=None,
        top_p=None,
        max_tokens=128,
        extra_body={"anthropic_prompt_cache": "5m"},
    )
    assert payload["system"] == [
        {
            "type": "text",
            "text": "stable-sys",
            "cache_control": {"type": "ephemeral", "ttl": "5m"},
        }
    ]
    assert "anthropic_prompt_cache" not in payload


def test_build_payload_applies_system_cache_1h() -> None:
    payload = _build_payload(
        model="claude-sonnet-4-5",
        messages=[
            {"role": "system", "content": "stable-sys"},
            {"role": "user", "content": "hi"},
        ],
        stream=False,
        temperature=None,
        top_p=None,
        max_tokens=128,
        extra_body={"anthropic_prompt_cache": "1h"},
    )
    assert payload["system"] == [
        {
            "type": "text",
            "text": "stable-sys",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]


def test_build_payload_cache_off_keeps_string_system() -> None:
    payload = _build_payload(
        model="claude-sonnet-4-5",
        messages=[
            {"role": "system", "content": "stable-sys"},
            {"role": "user", "content": "hi"},
        ],
        stream=False,
        temperature=None,
        top_p=None,
        max_tokens=128,
        extra_body={"anthropic_prompt_cache": "off"},
    )
    assert payload["system"] == "stable-sys"


def test_build_payload_maps_thinking_enabled() -> None:
    payload = _build_payload(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        temperature=0.7,
        top_p=0.9,
        max_tokens=128,
        extra_body={"thinking": {"type": "enabled"}, "reasoning": {"effort": "low"}},
    )
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert payload["temperature"] == 1
    assert "top_p" not in payload


def test_decode_usage_anthropic_shape() -> None:
    usage = decode_usage(
        {
            "input_tokens": 12,
            "output_tokens": 5,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 1,
        }
    )
    assert usage is not None
    assert usage.input_tokens == 12
    assert usage.output_tokens == 5
    assert usage.total_tokens == 17
    assert usage.cache_read_input_tokens == 3
    assert usage.cache_write_input_tokens == 1


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json_dumps(payload or {})
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        self.reason_phrase = "OK" if status_code < 400 else "Error"
        self.url = "https://api.anthropic.com/v1/messages"

    def json(self) -> dict[str, Any]:
        return self._payload


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj)


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._response

    async def get(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._response


def test_complete_nonstream_text() -> None:
    adapter = AnthropicMessagesAdapter()
    response = _FakeResponse(
        payload={
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 2, "output_tokens": 1},
        }
    )

    async def run() -> Any:
        with patch("app.llm.providers.anthropic_messages.get_async_http_client", return_value=_FakeClient(response)):
            return await adapter.complete(
                base_url="https://api.anthropic.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="claude-sonnet-4-5", max_tokens=32),
                as_message=True,
            )

    result = asyncio.run(run())
    assert result.content == "hello"
    assert result.tool_calls is None


class _FakeStreamResponse:
    def __init__(self, lines: list[str], *, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"content-type": "text/event-stream"}
        self.request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        self.reason_phrase = "OK"
        self.url = "https://api.anthropic.com/v1/messages"
        self._lines = lines
        self.text = ""

    async def aread(self) -> bytes:
        return b""

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self) -> "_FakeStreamResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class _FakeStreamClient:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    def stream(self, *args: Any, **kwargs: Any) -> _FakeStreamResponse:
        return self._response


def test_stream_yields_content_reasoning_and_finish() -> None:
    adapter = AnthropicMessagesAdapter()
    lines = [
        "event: message_start",
        'data: {"type":"message_start","message":{"usage":{"input_tokens":3}}}',
        "",
        "event: content_block_delta",
        'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"hmm"}}',
        "",
        "event: content_block_delta",
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}',
        "",
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ]
    response = _FakeStreamResponse(lines)

    async def run() -> list[Any]:
        out = []
        with patch("app.llm.providers.anthropic_messages.get_async_http_client", return_value=_FakeStreamClient(response)):
            async for chunk in adapter.stream(
                base_url="https://api.anthropic.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="claude-sonnet-4-5", max_tokens=32, stream=True),
            ):
                out.append(chunk)
        return out

    chunks = asyncio.run(run())
    kinds = [c.kind for c in chunks]
    assert "reasoning" in kinds
    assert "content" in kinds
    assert kinds[-1] == "finish"
    assert "".join(c.text for c in chunks if c.kind == "content") == "hi"
    assert "".join(c.text for c in chunks if c.kind == "reasoning") == "hmm"


def test_stream_tool_use_fast_fails() -> None:
    adapter = AnthropicMessagesAdapter()
    lines = [
        "event: content_block_start",
        'data: {"type":"content_block_start","content_block":{"type":"tool_use","id":"t1","name":"web_search"}}',
        "",
    ]
    response = _FakeStreamResponse(lines)

    async def run() -> None:
        with patch("app.llm.providers.anthropic_messages.get_async_http_client", return_value=_FakeStreamClient(response)):
            async for _ in adapter.stream(
                base_url="https://api.anthropic.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="claude-sonnet-4-5", max_tokens=32, stream=True),
            ):
                pass

    with pytest.raises(AppError) as exc:
        asyncio.run(run())
    assert exc.value.code == "provider_capability_unsupported"
