from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.errors import AppError
from app.llm.openai_compat import ChatCompletionMessage, StreamChunk
from app.schemas import Settings
from app.services.generate_web_search_runtime import (
    _parse_web_search_query,
    iter_web_search_stream_events,
    nonstream_web_search_rounds,
)


def test_web_search_tool_arguments_must_be_valid_json_object() -> None:
    tool_call = {
        "id": "call-1",
        "function": {
            "name": "web_search",
            "arguments": "{invalid-json}",
        },
    }

    try:
        _parse_web_search_query(tool_call)
    except AppError as error:
        assert error.code == "tool_call_invalid"
        assert error.status_code == 502
    else:
        raise AssertionError("expected AppError")


def test_web_search_tool_requires_non_empty_query() -> None:
    tool_call = {
        "id": "call-1",
        "function": {
            "name": "web_search",
            "arguments": '{"query":"   "}',
        },
    }

    try:
        _parse_web_search_query(tool_call)
    except AppError as error:
        assert error.code == "tool_call_invalid"
        assert "关键词" in error.message
    else:
        raise AssertionError("expected AppError")


def test_web_search_tool_returns_normalized_query() -> None:
    tool_call = {
        "id": "call-1",
        "function": {
            "name": "web_search",
            "arguments": '{"query":"  latest news  "}',
        },
    }

    assert _parse_web_search_query(tool_call) == "latest news"


def test_stream_runtime_does_not_execute_tool_with_invalid_arguments() -> None:
    async def fake_stream(**_kwargs):
        yield StreamChunk(
            kind="finish",
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{invalid-json}"},
                }
            ],
        )

    async def run() -> tuple[AppError, AsyncMock]:
        search = AsyncMock()
        with (
            patch(
                "app.services.generate_web_search_runtime.web_search_is_configured",
                return_value=True,
            ),
            patch(
                "app.services.generate_web_search_runtime.stream_chat_completions",
                fake_stream,
            ),
            patch(
                "app.services.generate_web_search_runtime.run_web_search",
                search,
            ),
        ):
            try:
                async for _event in iter_web_search_stream_events(
                    messages=[{"role": "user", "content": "hello"}],
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    temperature=None,
                    top_p=None,
                    max_tokens=None,
                    extra_body={},
                    settings=Settings(),
                    web_search_enabled=True,
                ):
                    pass
            except AppError as error:
                return error, search
        raise AssertionError("expected AppError")

    error, search = asyncio.run(run())
    assert error.code == "tool_call_invalid"
    search.assert_not_awaited()


def test_nonstream_runtime_does_not_execute_tool_with_invalid_arguments() -> None:
    response = ChatCompletionMessage(
        role="assistant",
        content=None,
        reasoning_content=None,
        tool_calls=[
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "web_search", "arguments": "{invalid-json}"},
            }
        ],
    )

    async def run() -> tuple[AppError, AsyncMock]:
        search = AsyncMock()
        with (
            patch(
                "app.services.generate_web_search_runtime.web_search_is_configured",
                return_value=True,
            ),
            patch(
                "app.services.generate_web_search_runtime.chat_completions_message",
                AsyncMock(return_value=response),
            ),
            patch(
                "app.services.generate_web_search_runtime.run_web_search",
                search,
            ),
        ):
            try:
                await nonstream_web_search_rounds(
                    messages=[{"role": "user", "content": "hello"}],
                    base_url="https://provider.example/v1",
                    api_key="test-key",
                    model="test-model",
                    temperature=None,
                    top_p=None,
                    max_tokens=None,
                    extra_body={},
                    settings=Settings(),
                    web_search_enabled=True,
                )
            except AppError as error:
                return error, search
        raise AssertionError("expected AppError")

    error, search = asyncio.run(run())
    assert error.code == "tool_call_invalid"
    search.assert_not_awaited()
