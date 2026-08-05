"""Protocol-aware LLM call helpers (T-805-5A).

Call sites pass credentials.protocol; unknown/unimplemented protocols fast-fail via registry.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.llm.registry import get_adapter
from app.llm.types import (
    OPENAI_COMPATIBLE_CHAT_PROTOCOL,
    GenerationConfig,
    normalize_protocol_id,
)
from app.llm.providers.openai_compatible_chat import (
    ChatCompletionMessage,
    ChatCompletionResult,
    StreamChunk,
)


def _config(
    *,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    tools: list[dict[str, Any]] | None,
    extra_body: dict[str, Any] | None,
    stream: bool,
) -> GenerationConfig:
    return GenerationConfig(
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=extra_body,
        stream=stream,
    )


async def list_models(*, base_url: str, api_key: str, protocol: str | None = None) -> list[str]:
    adapter = get_adapter(normalize_protocol_id(protocol))
    return await adapter.list_models(base_url=base_url, api_key=api_key)


async def chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
    protocol: str | None = None,
) -> ChatCompletionResult:
    adapter = get_adapter(normalize_protocol_id(protocol))
    result = await adapter.complete(
        base_url=base_url,
        api_key=api_key,
        messages=messages,
        config=_config(
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            extra_body=extra_body,
            stream=False,
        ),
        as_message=False,
    )
    return result


async def chat_completions_message(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
    protocol: str | None = None,
) -> ChatCompletionMessage:
    adapter = get_adapter(normalize_protocol_id(protocol))
    result = await adapter.complete(
        base_url=base_url,
        api_key=api_key,
        messages=messages,
        config=_config(
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            extra_body=extra_body,
            stream=False,
        ),
        as_message=True,
    )
    return result


async def stream_chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    extra_body: dict[str, Any] | None = None,
    protocol: str | None = None,
) -> AsyncIterator[StreamChunk]:
    adapter = get_adapter(normalize_protocol_id(protocol))
    async for chunk in adapter.stream(
        base_url=base_url,
        api_key=api_key,
        messages=messages,
        config=_config(
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            extra_body=extra_body,
            stream=True,
        ),
    ):
        yield chunk


__all__ = [
    "OPENAI_COMPATIBLE_CHAT_PROTOCOL",
    "chat_completions",
    "chat_completions_message",
    "list_models",
    "stream_chat_completions",
]
