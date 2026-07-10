import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app.errors import AppError
from app.llm.openai_compat import (
    _build_payload,
    _chat_completions_url,
    _models_url,
    _upstream_http_error_text,
    chat_completions,
    chat_completions_message,
    list_models_openai_compat,
    stream_chat_completions,
)


class _FakeResponseClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, _url: str, **_kwargs) -> httpx.Response:
        return self.response


class _FakeStreamContext:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeStreamClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, _method: str, _url: str, **_kwargs) -> _FakeStreamContext:
        return _FakeStreamContext(self.response)


def _response(payload: object) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    return httpx.Response(200, request=request, json=payload)


def _stream_response(raw: str) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    return httpx.Response(200, request=request, text=raw)


def test_chat_completions_url_adds_openai_v1_for_bare_host() -> None:
    assert _chat_completions_url("api.openai.com") == "https://api.openai.com/v1/chat/completions"


def test_chat_completions_url_preserves_provider_path() -> None:
    assert (
        _chat_completions_url("https://generativelanguage.googleapis.com/v1beta/openai")
        == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )


def test_chat_completions_url_does_not_duplicate_suffix() -> None:
    url = "https://example.com/v1/chat/completions"

    assert _chat_completions_url(url) == url
    assert _models_url(url) == "https://example.com/v1/models"


def test_upstream_http_error_text_extracts_openai_message() -> None:
    assert _upstream_http_error_text('{"error":{"message":"bad key","code":"401"}}') == "bad key: 401"


def test_build_payload_sets_max_completion_tokens_alias() -> None:
    payload = _build_payload(
        model="model",
        messages=[],
        stream=False,
        temperature=None,
        top_p=None,
        max_tokens=32,
        tools=None,
        extra_body=None,
    )

    assert payload["max_tokens"] == 32
    assert payload["max_completion_tokens"] == 32


def test_list_models_maps_401_instead_of_returning_empty_list() -> None:
    class UnauthorizedClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
            request = httpx.Request("GET", url, headers=headers)
            return httpx.Response(
                401,
                request=request,
                json={"error": {"message": "invalid key"}},
            )

    async def run() -> AppError:
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", UnauthorizedClient),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            try:
                await list_models_openai_compat("https://provider.example/v1", "bad-key")
            except AppError as error:
                return error
        raise AssertionError("expected AppError")

    error = asyncio.run(run())
    assert error.code == "provider_auth_failed"
    assert error.status_code == 401


def test_nonstream_empty_choices_fast_fails() -> None:
    async def run() -> AppError:
        client = _FakeResponseClient(_response({"choices": []}))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            try:
                await chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            except AppError as error:
                return error
        raise AssertionError("expected AppError")

    error = asyncio.run(run())
    assert error.code == "provider_response_invalid"
    assert "choices" in (error.detail or "")


def test_nonstream_message_allows_tool_call_without_text() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": '{"query":"news"}'},
                        }
                    ],
                }
            }
        ]
    }

    async def run():
        client = _FakeResponseClient(_response(payload))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            return await chat_completions_message(
                base_url="https://provider.example/v1",
                api_key="test-key",
                model="test-model",
                messages=[{"role": "user", "content": "hello"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            )

    result = asyncio.run(run())
    assert result.content is None
    assert result.tool_calls and result.tool_calls[0]["id"] == "call-1"


def test_stream_invalid_json_fast_fails() -> None:
    async def run() -> AppError:
        client = _FakeStreamClient(_stream_response("data: {invalid-json}\n\n"))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            try:
                async for _chunk in stream_chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                ):
                    pass
            except AppError as error:
                return error
        raise AssertionError("expected AppError")

    error = asyncio.run(run())
    assert error.code == "stream_event_invalid"


def test_stream_allows_keepalive_usage_and_normal_completion() -> None:
    raw = "\n".join(
        [
            ": keepalive",
            "",
            'data: {"choices":[],"usage":{"prompt_tokens":1}}',
            "",
            'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}',
            "",
            "data: [DONE]",
            "",
        ]
    )

    async def run():
        client = _FakeStreamClient(_stream_response(raw))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            return [
                chunk
                async for chunk in stream_chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            ]

    chunks = asyncio.run(run())
    assert "".join(chunk.text for chunk in chunks if chunk.kind == "content") == "ok"
    assert chunks[-1].kind == "finish"


def test_stream_without_done_or_finish_reason_is_interrupted() -> None:
    raw = 'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":null}]}\n\n'

    async def run() -> tuple[str, AppError]:
        client = _FakeStreamClient(_stream_response(raw))
        content: list[str] = []
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            try:
                async for chunk in stream_chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                ):
                    if chunk.kind == "content":
                        content.append(chunk.text)
            except AppError as error:
                return "".join(content), error
        raise AssertionError("expected AppError")

    content, error = asyncio.run(run())
    assert content == "partial"
    assert error.code == "stream_interrupted"
    assert error.retryable is True


def test_stream_empty_completion_fast_fails() -> None:
    raw = "\n".join(
        [
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "",
            "data: [DONE]",
            "",
        ]
    )

    async def run() -> AppError:
        client = _FakeStreamClient(_stream_response(raw))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            try:
                async for _chunk in stream_chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                ):
                    pass
            except AppError as error:
                return error
        raise AssertionError("expected AppError")

    error = asyncio.run(run())
    assert error.code == "provider_response_invalid"


def test_stream_reasoning_and_tool_call_can_finish_without_done_sentinel() -> None:
    raw = "\n".join(
        [
            'data: {"choices":[{"delta":{"reasoning_content":"think"},"finish_reason":null}]}',
            "",
            (
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
                '"function":{"name":"web_search","arguments":"{\\"query\\":\\"news\\"}"}}]},'
                '"finish_reason":"tool_calls"}]}'
            ),
            "",
        ]
    )

    async def run():
        client = _FakeStreamClient(_stream_response(raw))
        with (
            patch("app.llm.openai_compat.httpx.AsyncClient", return_value=client),
            patch("app.services.http_log._write_record", AsyncMock()),
        ):
            return [
                chunk
                async for chunk in stream_chat_completions(
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                    tools=[{"type": "function", "function": {"name": "web_search"}}],
                )
            ]

    chunks = asyncio.run(run())
    assert "".join(chunk.text for chunk in chunks if chunk.kind == "reasoning") == "think"
    assert chunks[-1].kind == "finish"
    assert chunks[-1].tool_calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "web_search", "arguments": '{"query":"news"}'},
        }
    ]
