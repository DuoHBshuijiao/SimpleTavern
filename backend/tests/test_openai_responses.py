"""T-805-5D / T-806-6B: OpenAI Responses adapter (function tools round-trip)."""

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
    _convert_tools,
    _responses_url,
    decode_usage,
)
from app.llm.registry import get_adapter, registered_protocols, reset_adapter_registry_for_tests
from app.llm.types import OPENAI_RESPONSES_PROTOCOL, GenerationConfig

_SAMPLE_CHAT_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    },
}


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


def test_convert_input_tool_round_trip() -> None:
    instructions, items = _convert_input(
        [
            {"role": "user", "content": "weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"location":"Paris"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": '{"temp":20}'},
        ]
    )
    assert instructions is None
    assert items[0] == {"role": "user", "content": "weather?"}
    assert items[1] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "get_weather",
        "arguments": '{"location":"Paris"}',
    }
    assert items[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"temp":20}',
    }


def test_convert_tools_chat_to_responses() -> None:
    converted = _convert_tools([_SAMPLE_CHAT_TOOL])
    assert converted == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
    ]


def test_function_tools_build_request() -> None:
    adapter = OpenAIResponsesAdapter()
    req = adapter.build_request(
        base_url="https://api.openai.com",
        api_key="k",
        messages=[
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_abc", "content": "ok"},
        ],
        config=GenerationConfig(
            model="gpt-4.1",
            tools=[_SAMPLE_CHAT_TOOL],
            tool_choice="auto",
        ),
    )
    body = req.json_body or {}
    assert body["tools"] == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
    ]
    assert body["tool_choice"] == "auto"
    assert body["input"][-2]["type"] == "function_call"
    assert body["input"][-1]["type"] == "function_call_output"


def test_builtin_web_search_tool_rejected() -> None:
    adapter = OpenAIResponsesAdapter()
    with pytest.raises(AppError) as exc:
        adapter.build_request(
            base_url="https://api.openai.com",
            api_key="k",
            messages=[{"role": "user", "content": "hi"}],
            config=GenerationConfig(model="gpt-4.1", tools=[{"type": "web_search"}]),
        )
    assert exc.value.code == "provider_capability_unsupported"
    assert "web_search" in (exc.value.detail or "")


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
    assert result.tool_calls is None


def test_complete_function_call_as_message() -> None:
    adapter = OpenAIResponsesAdapter()
    response = _FakeResponse(
        payload={
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "get_weather",
                    "arguments": '{"location":"Paris"}',
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        }
    )

    async def run() -> Any:
        with patch("app.llm.providers.openai_responses.get_async_http_client", return_value=_FakeClient(response)):
            return await adapter.complete(
                base_url="https://api.openai.com",
                api_key="k",
                messages=[{"role": "user", "content": "weather?"}],
                config=GenerationConfig(model="gpt-4.1", tools=[_SAMPLE_CHAT_TOOL]),
                as_message=True,
            )

    result = asyncio.run(run())
    assert result.content == ""
    assert result.tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"Paris"}'},
        }
    ]


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
    assert chunks[-1].tool_calls is None


def test_stream_function_call_finish() -> None:
    adapter = OpenAIResponsesAdapter()

    def _sse(event: str, payload: dict[str, Any]) -> list[str]:
        return [f"event: {event}", f"data: {json.dumps(payload, ensure_ascii=False)}", ""]

    lines = [
        *_sse(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "get_weather",
                    "arguments": "",
                },
            },
        ),
        *_sse(
            "response.function_call_arguments.delta",
            {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"location":'},
        ),
        *_sse(
            "response.function_call_arguments.delta",
            {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '"Paris"}'},
        ),
        *_sse(
            "response.function_call_arguments.done",
            {
                "type": "response.function_call_arguments.done",
                "item_id": "fc_1",
                "arguments": '{"location":"Paris"}',
            },
        ),
        *_sse(
            "response.completed",
            {
                "type": "response.completed",
                "response": {"usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}},
            },
        ),
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
                messages=[{"role": "user", "content": "weather?"}],
                config=GenerationConfig(model="gpt-4.1", stream=True, tools=[_SAMPLE_CHAT_TOOL]),
            ):
                out.append(chunk)
        return out

    chunks = asyncio.run(run())
    assert chunks[-1].kind == "finish"
    assert chunks[-1].tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"Paris"}'},
        }
    ]


def test_stream_builtin_web_search_fast_fails() -> None:
    adapter = OpenAIResponsesAdapter()
    lines = [
        "event: response.output_item.added",
        'data: {"type":"response.output_item.added","item":{"type":"web_search_call","id":"ws_1"}}',
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
