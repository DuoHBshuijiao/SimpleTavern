"""T-805-5C: Gemini generateContent adapter (no tools; not OpenAI-compat shim)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.errors import AppError
from app.llm.providers.gemini_generate_content import (
    GeminiGenerateContentAdapter,
    _api_root,
    _build_payload,
    _convert_messages,
    _model_action_url,
    decode_usage,
)
from app.llm.registry import get_adapter, registered_protocols, reset_adapter_registry_for_tests
from app.llm.types import GEMINI_GENERATE_CONTENT_PROTOCOL, GenerationConfig


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_adapter_registry_for_tests()
    yield
    reset_adapter_registry_for_tests()


def test_registry_resolves_gemini() -> None:
    adapter = get_adapter(GEMINI_GENERATE_CONTENT_PROTOCOL)
    assert isinstance(adapter, GeminiGenerateContentAdapter)
    assert GEMINI_GENERATE_CONTENT_PROTOCOL in registered_protocols()


def test_rejects_openai_compat_base_url() -> None:
    with pytest.raises(AppError) as exc:
        _api_root("https://generativelanguage.googleapis.com/v1beta/openai")
    assert exc.value.code == "provider_request_invalid"
    assert "openai" in (exc.value.detail or "").lower()


def test_model_action_urls() -> None:
    base = "https://generativelanguage.googleapis.com"
    assert (
        _model_action_url(base, model="gemini-2.5-flash", stream=False)
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    stream_url = _model_action_url(base, model="models/gemini-2.5-flash", stream=True)
    assert stream_url.startswith(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent"
    )
    assert "alt=sse" in stream_url


def test_convert_messages_maps_roles_and_system() -> None:
    system, contents = _convert_messages(
        [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "more"},
        ]
    )
    assert system == {"parts": [{"text": "be helpful"}]}
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert contents[2]["role"] == "user"


def test_tools_fast_fail() -> None:
    adapter = GeminiGenerateContentAdapter()
    with pytest.raises(AppError) as exc:
        adapter.build_request(
            base_url="https://generativelanguage.googleapis.com",
            api_key="k",
            messages=[{"role": "user", "content": "hi"}],
            config=GenerationConfig(model="gemini-2.5-flash", tools=[{"type": "function"}]),
        )
    assert exc.value.code == "provider_capability_unsupported"


def test_build_payload_thinking_and_defaults() -> None:
    payload = _build_payload(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.4,
        top_p=0.8,
        max_tokens=None,
        extra_body={"thinking": {"type": "enabled"}, "reasoning": {"effort": "high"}, "cachedContent": "x"},
    )
    assert payload["generationConfig"]["maxOutputTokens"] == 4096
    assert payload["generationConfig"]["temperature"] == 0.4
    assert payload["generationConfig"]["topP"] == 0.8
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 8192}
    assert "cachedContent" not in payload


def test_decode_usage_gemini_shape() -> None:
    usage = decode_usage(
        {
            "promptTokenCount": 10,
            "candidatesTokenCount": 4,
            "totalTokenCount": 14,
            "cachedContentTokenCount": 2,
            "thoughtsTokenCount": 3,
        }
    )
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.output_tokens == 4
    assert usage.total_tokens == 14
    assert usage.cache_read_input_tokens == 2
    assert usage.reasoning_tokens == 3


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/m:generateContent")
        self.reason_phrase = "OK" if status_code < 400 else "Error"
        self.url = self.request.url

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._response

    async def get(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._response


def test_complete_nonstream() -> None:
    adapter = GeminiGenerateContentAdapter()
    response = _FakeResponse(
        payload={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "think", "thought": True},
                            {"text": "hello"},
                        ]
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
        }
    )

    async def run() -> Any:
        with patch("app.llm.providers.gemini_generate_content.get_async_http_client", return_value=_FakeClient(response)):
            return await adapter.complete(
                base_url="https://generativelanguage.googleapis.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gemini-2.5-flash"),
                as_message=True,
            )

    result = asyncio.run(run())
    assert result.content == "hello"
    assert result.reasoning_content == "think"


class _FakeStreamResponse:
    def __init__(self, lines: list[str], *, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"content-type": "text/event-stream"}
        self.request = httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/m:streamGenerateContent?alt=sse",
        )
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


def test_stream_yields_content_and_finish() -> None:
    adapter = GeminiGenerateContentAdapter()
    lines = [
        'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}',
        "",
        'data: {"candidates":[{"content":{"parts":[{"text":"!"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":2,"totalTokenCount":3}}',
        "",
    ]

    async def run() -> list[Any]:
        out = []
        with patch(
            "app.llm.providers.gemini_generate_content.get_async_http_client",
            return_value=_FakeStreamClient(_FakeStreamResponse(lines)),
        ):
            async for chunk in adapter.stream(
                base_url="https://generativelanguage.googleapis.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gemini-2.5-flash", stream=True),
            ):
                out.append(chunk)
        return out

    chunks = asyncio.run(run())
    assert "".join(c.text for c in chunks if c.kind == "content") == "hi!"
    assert chunks[-1].kind == "finish"


def test_stream_function_call_fast_fails() -> None:
    adapter = GeminiGenerateContentAdapter()
    lines = [
        'data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"web_search","args":{}}}]}}]}',
        "",
    ]

    async def run() -> None:
        with patch(
            "app.llm.providers.gemini_generate_content.get_async_http_client",
            return_value=_FakeStreamClient(_FakeStreamResponse(lines)),
        ):
            async for _ in adapter.stream(
                base_url="https://generativelanguage.googleapis.com",
                api_key="k",
                messages=[{"role": "user", "content": "hi"}],
                config=GenerationConfig(model="gemini-2.5-flash", stream=True),
            ):
                pass

    with pytest.raises(AppError) as exc:
        asyncio.run(run())
    assert exc.value.code == "provider_capability_unsupported"
