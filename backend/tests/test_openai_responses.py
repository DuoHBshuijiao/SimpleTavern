"""T-805-5D: OpenAI Responses adapter (no tools; typed SSE)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.errors import AppError
from app.llm.providers.openai_responses import (
    OpenAIResponsesAdapter,
    _build_payload,
    _convert_input,
    _responses_url,
    decode_usage,
)
from app.llm.registry import get_adapter, registered_protocols, reset_adapter_registry_for_tests
from app.llm.types import OPENAI_RESPONSES_PROTOCOL, GenerationConfig


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_adapter_registry_for_tests()
    yield
    reset_adapter_registry_for_tests()


def test_registry_resolves_openai_responses() -> None:
    adapter = get_adapter(OPENAI_RESPONSES_PROTOCOL)
    assert isinstance(adapter, OpenAIResponsesAdapter)
    assert OPENAI_RESPONSES_PROTOCOL in registered_protocols()


def test_responses_url_normalizes() -> None:
    assert _responses_url("api.openai.com") == "https://api.openai.com/v1/responses"
    assert _responses_url("https://api.openai.com/v1/chat/completions") == "https://api.openai.com/v1/responses"
    assert _responses_url("https://api.openai.com/v1/responses") == "https://api.openai.com/v1/responses"


def test_convert_input_extracts_instructions() -> None:
    instructions, items = _convert_input(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert instructions == "sys"
    assert items == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_tools_fast_fail() -> None:
    adapter = OpenAIResponsesAdapter()
    with pytest.raises(AppError) as exc:
        adapter.build_request(
            base_url="https://api.openai.com",
            api_key="k",
            messages=[{"role": "user", "content": "hi"}],
            config=GenerationConfig(model="gpt-4.1", tools=[{"type": "web_search"}]),
        )
    assert exc.value.code == "provider_capability_unsupported"


def test_build_payload_defaults_and_reasoning() -> None:
    payload = _build_payload(
        model="gpt-4.1",
        messages=[{"role": "system", "content": "be nice"}, {"role": "user", "content": "hi"}],
        stream=True,
        temperature=0.5,
        top_p=None,
        max_tokens=None,
        extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "low", "tools": None},
    )
    assert payload["instructions"] == "be nice"
    assert payload["max_output_tokens"] == 4096
    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["reasoning"] == {"effort": "low", "summary": "auto"}
    assert "temperature" not in payload  # dropped when reasoning enabled
    assert "tools" not in payload


def test_decode_usage_responses_shape() -> None:
    usage = decode_usage(
        {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 8},
        }
    )
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 20
    assert usage.total_tokens == 30
    assert usage.cache_read_input_tokens == 2
    assert usage.reasoning_tokens == 8


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        self.reason_phrase = "OK" if status_code < 400 else "Error"
        self.url = self.request.url

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._response


def test_complete_nonstream() -> None:
    adapter = OpenAIResponsesAdapter()
    response = _FakeResponse(
        payload={
            "output": [
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "think"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello"}],
                },
            ],
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        }
    )

    async def run() -> Any:
        with patch("app.llm.providers.openai_responses.get_async_http_client", return_value=_FakeClient(response)):
            return await adapter.complete(
                base_url="https://api.openai.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gpt-4.1"),
                as_message=True,
            )

    result = asyncio.run(run())
    assert result.content == "hello"
    assert result.reasoning_content == "think"


class _FakeStreamResponse:
    def __init__(self, lines: list[str], *, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"content-type": "text/event-stream"}
        self.request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        self.reason_phrase = "OK"
        self.url = self.request.url
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


def test_stream_typed_sse() -> None:
    adapter = OpenAIResponsesAdapter()
    lines = [
        "event: response.created",
        'data: {"type":"response.created"}',
        "",
        "event: response.reasoning_summary_text.delta",
        'data: {"type":"response.reasoning_summary_text.delta","delta":"hmm"}',
        "",
        "event: response.output_text.delta",
        'data: {"type":"response.output_text.delta","delta":"hi"}',
        "",
        "event: response.completed",
        'data: {"type":"response.completed","response":{"usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3}}}',
        "",
    ]

    async def run() -> list[Any]:
        out = []
        with patch(
            "app.llm.providers.openai_responses.get_async_http_client",
            return_value=_FakeStreamClient(_FakeStreamResponse(lines)),
        ):
            async for chunk in adapter.stream(
                base_url="https://api.openai.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gpt-4.1", stream=True),
            ):
                out.append(chunk)
        return out

    chunks = asyncio.run(run())
    assert "".join(c.text for c in chunks if c.kind == "reasoning") == "hmm"
    assert "".join(c.text for c in chunks if c.kind == "content") == "hi"
    assert chunks[-1].kind == "finish"


def test_stream_function_call_fast_fails() -> None:
    adapter = OpenAIResponsesAdapter()
    lines = [
        "event: response.output_item.added",
        'data: {"type":"response.output_item.added","item":{"type":"function_call","name":"web_search"}}',
        "",
    ]

    async def run() -> None:
        with patch(
            "app.llm.providers.openai_responses.get_async_http_client",
            return_value=_FakeStreamClient(_FakeStreamResponse(lines)),
        ):
            async for _ in adapter.stream(
                base_url="https://api.openai.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gpt-4.1", stream=True),
            ):
                pass

    with pytest.raises(AppError) as exc:
        asyncio.run(run())
    assert exc.value.code == "provider_capability_unsupported"
