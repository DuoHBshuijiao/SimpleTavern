"""
OpenAI兼容 API 兼容门面（T-804）。

真实实现位于 `app.llm.providers.openai_compatible_chat`。
本模块保持历史公开 ABI，供 generate / assistant / TTS / 测试继续导入。
"""

from __future__ import annotations

from app.llm.providers.openai_compatible_chat import (  # noqa: F401
    STREAM_TEXT_CHUNK_SIZE,
    ChatCompletionDelta,
    ChatCompletionMessage,
    ChatCompletionResult,
    OpenAICompatibleChatAdapter,
    StreamChunk,
    _build_payload,
    _chat_completions_url,
    _common_headers,
    _models_url,
    _normalize_base_url,
    _upstream_http_error_text,
    chat_completions,
    chat_completions_message,
    decode_usage,
    list_models_openai_compat,
    stream_chat_completions,
)
from app.services.http_client import get_async_http_client  # noqa: F401  # tests patch this path

__all__ = [
    "STREAM_TEXT_CHUNK_SIZE",
    "ChatCompletionDelta",
    "ChatCompletionMessage",
    "ChatCompletionResult",
    "OpenAICompatibleChatAdapter",
    "StreamChunk",
    "_build_payload",
    "_chat_completions_url",
    "_common_headers",
    "_models_url",
    "_normalize_base_url",
    "_upstream_http_error_text",
    "chat_completions",
    "chat_completions_message",
    "decode_usage",
    "get_async_http_client",
    "list_models_openai_compat",
    "stream_chat_completions",
]
