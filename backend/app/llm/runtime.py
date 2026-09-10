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
    pop_control_block,
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
    """把 extra_body 里的 ``ST_CONTROL_KEY`` 控制块拆到 GenerationConfig 结构化字段（T-821/T-824）。"""
    remaining, control = pop_control_block(extra_body)
    headers = control.get("extra_headers")
    provider_params = control.get("provider_params")
    return GenerationConfig(
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=remaining,
        stream=stream,
        prompt_cache=control.get("prompt_cache") if isinstance(control.get("prompt_cache"), dict) else None,
        extra_headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) and headers else None,
        auth_style=control.get("auth_style") or None,
        protocol_variant=control.get("protocol_variant") or None,
        provider_params={str(k): str(v) for k, v in provider_params.items()} if isinstance(provider_params, dict) and provider_params else None,
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
