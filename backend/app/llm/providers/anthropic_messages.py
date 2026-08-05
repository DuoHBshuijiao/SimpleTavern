"""
Anthropic Messages API provider adapter (T-805-5B).

Scope for 5B:
- non-stream + stream text (and thinking→reasoning) paths
- tools / tool_result / tool_use → provider_capability_unsupported (T-806)
- prompt caching left off (no cache_control); T-806 owns off/5m/1h
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.errors import AppError, as_app_error
from app.llm.providers.openai_compatible_chat import (
    STREAM_TEXT_CHUNK_SIZE,
    ChatCompletionMessage,
    ChatCompletionResult,
    StreamChunk,
)
from app.llm.types import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GenerationConfig,
    Usage,
    WireRequest,
)
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound

_PROVIDER = "anthropic"
_PROTOCOL = ANTHROPIC_MESSAGES_PROTOCOL
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096
_MAX_ERROR_BODY_CHARS = 12000
_MESSAGES_SUFFIX = "/messages"

_THINKING_BUDGET_BY_EFFORT: dict[str, int] = {
    "minimal": 1024,
    "low": 2048,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
}


def _protocol_error(
    *,
    code: str,
    message: str,
    detail: str,
    retryable: bool = False,
    status_code: int = 502,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        detail=detail,
        source="llm.anthropic_messages",
        status_code=status_code,
        retryable=retryable,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="检查 Anthropic API 预设（Base URL / API Key / 模型）与协议是否匹配",
    )


def _tools_unsupported(*, detail: str) -> AppError:
    return AppError(
        code="provider_capability_unsupported",
        message="当前 Anthropic Messages 适配器尚未支持工具调用",
        detail=detail,
        source="llm.anthropic_messages",
        status_code=400,
        retryable=False,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="请改用 OpenAI Compatible Chat，或等待 T-806 工具支持后再启用工具/网络搜索",
    )


def _upstream_http_error_text(body: str) -> str:
    raw = (body or "").strip()
    if not raw:
        return "(empty response body)"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:_MAX_ERROR_BODY_CHARS]
    if not isinstance(data, dict):
        return raw[:_MAX_ERROR_BODY_CHARS]
    err = data.get("error")
    if isinstance(err, dict):
        m = err.get("message")
        if isinstance(m, str) and m.strip():
            typ = err.get("type")
            return f"{m.strip()}" + (f" ({typ})" if typ else "")
    if isinstance(err, str) and err.strip():
        return err.strip()
    m = data.get("message")
    if isinstance(m, str) and m.strip():
        return m.strip()
    return raw[:_MAX_ERROR_BODY_CHARS]


def _raise_http_error(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    detail = _upstream_http_error_text(r.text or "")
    msg = f"HTTP {r.status_code} {r.reason_phrase} for {r.url}\n{detail}"
    raise httpx.HTTPStatusError(msg, request=r.request, response=r)


async def _raise_stream_http_error(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    await r.aread()
    detail = _upstream_http_error_text(r.text or "")
    msg = f"HTTP {r.status_code} {r.reason_phrase} for {r.url}\n{detail}"
    raise httpx.HTTPStatusError(msg, request=r.request, response=r)


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip()
    if not base:
        return base
    if not (base.startswith("http://") or base.startswith("https://")):
        base = "https://" + base
    base = base.rstrip("/")
    parts = urlsplit(base)
    path = parts.path or ""
    if not path or path == "/":
        return urlunsplit((parts.scheme, parts.netloc, "/v1", parts.query, parts.fragment))
    return base


def _messages_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("API 基础地址未配置或为空。请填写 Anthropic Base URL（如 https://api.anthropic.com）。")
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    lower = raw.lower()
    if lower.endswith(_MESSAGES_SUFFIX) or lower.endswith(_MESSAGES_SUFFIX + "/"):
        return raw.rstrip("/")
    return _normalize_base_url(raw) + _MESSAGES_SUFFIX


def _models_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("API 基础地址未配置或为空。")
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    lower = raw.lower()
    if lower.endswith(_MESSAGES_SUFFIX):
        raw = raw[: -len(_MESSAGES_SUFFIX)].rstrip("/")
    return _normalize_base_url(raw) + "/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key.strip(),
        "anthropic-version": _ANTHROPIC_VERSION,
    }


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _to_anthropic_content(content: Any) -> str | list[dict[str, Any]]:
    """Map OpenAI-ish content to Anthropic content (text-only for 5B)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    blocks.append({"type": "text", "text": item})
                continue
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ == "text" or "text" in item:
                text = item.get("text")
                if isinstance(text, str) and text:
                    blocks.append({"type": "text", "text": text})
            elif typ == "image_url":
                # Multimodal image mapping deferred; keep text-only path honest.
                raise _protocol_error(
                    code="provider_capability_unsupported",
                    message="当前 Anthropic Messages 适配器尚未支持图片输入",
                    detail="image_url content parts are not supported in T-805-5B",
                    status_code=400,
                )
        return blocks if blocks else ""
    return str(content)


def _reject_tools_in_messages(messages: list[dict[str, Any]]) -> None:
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "tool":
            raise _tools_unsupported(detail=f"messages[{idx}].role=tool")
        if msg.get("tool_calls"):
            raise _tools_unsupported(detail=f"messages[{idx}].tool_calls present")
        if msg.get("tool_call_id"):
            raise _tools_unsupported(detail=f"messages[{idx}].tool_call_id present")


def _reject_tools_in_config(config: GenerationConfig) -> None:
    if config.tools:
        raise _tools_unsupported(detail="GenerationConfig.tools is set")
    if config.tool_choice is not None:
        raise _tools_unsupported(detail="GenerationConfig.tool_choice is set")
    extra = config.extra_body or {}
    if extra.get("tools") or extra.get("tool_choice") is not None:
        raise _tools_unsupported(detail="extra_body contains tools/tool_choice")


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    _reject_tools_in_messages(messages)
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").strip()
        content = msg.get("content")
        if role == "system":
            text = _content_to_text(content).strip()
            if text:
                system_parts.append(text)
            continue
        if role not in {"user", "assistant"}:
            raise _protocol_error(
                code="provider_request_invalid",
                message="消息角色不被 Anthropic Messages 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
        anth_content = _to_anthropic_content(content)
        if converted and converted[-1]["role"] == role:
            # Merge consecutive same-role turns (Anthropic prefers alternation).
            prev = converted[-1]["content"]
            merged_text = _content_to_text(prev) + "\n" + _content_to_text(anth_content)
            converted[-1] = {"role": role, "content": merged_text}
        else:
            converted.append({"role": role, "content": anth_content})

    if converted and converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": "."})

    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _sanitize_extra_body(extra_body: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """
    Map shared reasoning extra_body into Anthropic thinking; strip OpenAI-only keys.
    Returns (payload_fragment, thinking_enabled).
    """
    if not extra_body:
        return {}, False
    out: dict[str, Any] = {}
    thinking_enabled = False

    thinking = extra_body.get("thinking")
    effort = None
    if isinstance(extra_body.get("reasoning"), dict):
        effort = extra_body["reasoning"].get("effort")
    if effort is None:
        effort = extra_body.get("reasoning_effort")

    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        thinking_enabled = True
        budget = _THINKING_BUDGET_BY_EFFORT.get(str(effort or "medium").lower(), 4096)
        out["thinking"] = {"type": "enabled", "budget_tokens": budget}
    elif isinstance(thinking, dict) and thinking.get("type") == "disabled":
        thinking_enabled = False
        # Omit thinking entirely when disabled.

    # Pass through Anthropic-native keys if callers set them explicitly (no cache_control in 5B).
    for key, value in extra_body.items():
        if key in {"thinking", "reasoning", "reasoning_effort", "tools", "tool_choice", "cache_control"}:
            continue
        if key == "system":
            continue
        out[key] = value

    return out, thinking_enabled


def _build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    system, anth_messages = _convert_messages(messages)
    if not anth_messages:
        raise _protocol_error(
            code="provider_request_invalid",
            message="没有可发送给 Anthropic 的对话消息",
            detail="messages empty after system extraction",
            status_code=400,
        )

    extra, thinking_enabled = _sanitize_extra_body(extra_body)
    payload: dict[str, Any] = {
        "model": model,
        "messages": anth_messages,
        "max_tokens": int(max_tokens) if max_tokens and max_tokens > 0 else _DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    if system:
        payload["system"] = system
    if thinking_enabled:
        # Anthropic requires temperature=1 (or omit) when thinking is enabled.
        payload["temperature"] = 1
    elif temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None and not thinking_enabled:
        payload["top_p"] = top_p
    payload.update(extra)
    # 5B: never enable prompt caching.
    payload.pop("cache_control", None)
    return payload


def _decode_json_object(response: httpx.Response, *, context: str) -> dict[str, Any]:
    try:
        data = response.json()
    except (TypeError, json.JSONDecodeError) as exc:
        raise _protocol_error(
            code="provider_response_invalid",
            message="上游服务返回了无法解析的 JSON",
            detail=f"{context}: {exc}",
        ) from exc
    if not isinstance(data, dict):
        raise _protocol_error(
            code="provider_response_invalid",
            message="上游服务返回了无效响应",
            detail=f"{context}: expected object, got {type(data).__name__}",
        )
    return data


def _extract_text_and_thinking(content_blocks: Any) -> tuple[str, str | None]:
    texts: list[str] = []
    thinking: list[str] = []
    if not isinstance(content_blocks, list):
        return "", None
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        typ = block.get("type")
        if typ == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif typ == "thinking" and isinstance(block.get("thinking"), str):
            thinking.append(block["thinking"])
        elif typ == "tool_use":
            raise _tools_unsupported(detail="assistant response contains tool_use block")
    text = "".join(texts)
    reasoning = "".join(thinking).strip() or None
    return text, reasoning


def _iter_text_chunks(text: str) -> list[str]:
    if not text:
        return []
    size = max(1, STREAM_TEXT_CHUNK_SIZE)
    return [text[i : i + size] for i in range(0, len(text), size)]


def decode_usage(raw: dict[str, Any] | None) -> Usage | None:
    """Normalize Anthropic usage; prefer terminal message_delta / final message usage."""
    if not isinstance(raw, dict) or not raw:
        return None

    def _as_int(val: Any) -> int | None:
        if isinstance(val, bool):
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float) and val.is_integer():
            return int(val)
        return None

    input_tokens = _as_int(raw.get("input_tokens"))
    output_tokens = _as_int(raw.get("output_tokens"))
    cache_read = _as_int(raw.get("cache_read_input_tokens"))
    cache_write = _as_int(raw.get("cache_creation_input_tokens"))
    if input_tokens is None and output_tokens is None and cache_read is None and cache_write is None:
        return None
    total = None
    if input_tokens is not None or output_tokens is not None:
        total = (input_tokens or 0) + (output_tokens or 0)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cache_read_input_tokens=cache_read,
        cache_write_input_tokens=cache_write,
        reasoning_tokens=None,
        raw=dict(raw),
    )


async def list_models_anthropic(*, base_url: str, api_key: str) -> list[str]:
    url = _models_url(base_url)
    headers = {
        "Accept": "application/json",
        **_auth_headers(api_key),
    }
    try:
        async with log_outbound(
            source="llm",
            method="GET",
            url=url,
            request_headers=headers,
            streaming=False,
        ) as _log:
            client = get_async_http_client()
            r = await client.get(url, headers=headers, timeout=60)
            _log.set_response(status=r.status_code, headers=dict(r.headers), text=r.text)
            _raise_http_error(r)
            data = _decode_json_object(r, context="anthropic models")
            _log.set_response(body=data)
            raw_data = data.get("data")
            if not isinstance(raw_data, list):
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效模型列表",
                    detail="models.data is missing or not a list",
                )
            out: list[str] = []
            for item in raw_data:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    out.append(model_id.strip())
            return sorted(set(out))
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.anthropic_messages.models",
            default_code="provider_request_failed",
            default_message="获取 Anthropic 模型列表失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def complete_anthropic(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
    as_message: bool = False,
) -> ChatCompletionResult | ChatCompletionMessage:
    _reject_tools_in_config(config)
    url = _messages_url(base_url)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }
    payload = _build_payload(
        model=config.model,
        messages=messages,
        stream=False,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
        extra_body=config.extra_body,
    )
    try:
        async with log_outbound(
            source="llm",
            method="POST",
            url=url,
            request_headers=headers,
            request_body=payload,
            streaming=False,
        ) as _log:
            client = get_async_http_client()
            r = await client.post(url, headers=headers, json=payload, timeout=120)
            _log.set_response(status=r.status_code, headers=dict(r.headers), text=r.text)
            _raise_http_error(r)
            data = _decode_json_object(r, context="anthropic messages")
            _log.set_response(body=data)
            text, reasoning = _extract_text_and_thinking(data.get("content"))
            # Terminal usage for future T-807.
            _ = decode_usage(data.get("usage") if isinstance(data.get("usage"), dict) else None)
            if as_message:
                return ChatCompletionMessage(
                    role="assistant",
                    content=text,
                    reasoning_content=reasoning,
                    tool_calls=None,
                )
            if not text.strip() and not reasoning:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游服务未返回有效文本",
                    detail="anthropic messages: empty text and thinking",
                )
            return ChatCompletionResult(text=text)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.anthropic_messages",
            default_code="provider_request_failed",
            default_message="Anthropic 请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def stream_anthropic(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
) -> AsyncIterator[StreamChunk]:
    _reject_tools_in_config(config)
    url = _messages_url(base_url)
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }
    payload = _build_payload(
        model=config.model,
        messages=messages,
        stream=True,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
        extra_body=config.extra_body,
    )

    saw_output = False
    terminal_usage: dict[str, Any] | None = None

    try:
        async with log_outbound(
            source="llm",
            method="POST",
            url=url,
            request_headers=headers,
            request_body=payload,
            streaming=True,
        ) as _log:
            aggregated_content: list[str] = []
            aggregated_reasoning: list[str] = []
            client = get_async_http_client()
            async with client.stream("POST", url, headers=headers, json=payload, timeout=None) as r:
                _log.set_response(status=r.status_code, headers=dict(r.headers))
                await _raise_stream_http_error(r)

                event_name = ""
                async for line in r.aiter_lines():
                    if line is None:
                        continue
                    if not line:
                        event_name = ""
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_name = line[len("event:") :].strip()
                        continue
                    if not line.startswith("data:"):
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流包含未知事件帧",
                            detail=f"unexpected SSE line: {line[:200]}",
                        )
                    data_str = line[len("data:") :].strip()
                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError as exc:
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流包含无法解析的 JSON",
                            detail=str(exc),
                        ) from exc
                    if not isinstance(data, dict):
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流事件不是对象",
                            detail=f"got {type(data).__name__}",
                        )

                    etype = event_name or str(data.get("type") or "")
                    if etype in {"ping", "message_start", "content_block_stop", "message_stop"}:
                        continue
                    if etype == "error":
                        err = data.get("error") if isinstance(data.get("error"), dict) else data
                        msg = ""
                        if isinstance(err, dict):
                            msg = str(err.get("message") or err.get("type") or "")
                        raise _protocol_error(
                            code="provider_request_failed",
                            message="Anthropic 流式返回错误",
                            detail=msg or data_str[:500],
                            retryable=True,
                        )
                    if etype == "content_block_start":
                        block = data.get("content_block")
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            raise _tools_unsupported(detail="stream content_block_start tool_use")
                        continue
                    if etype == "content_block_delta":
                        delta = data.get("delta")
                        if not isinstance(delta, dict):
                            continue
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                saw_output = True
                                aggregated_content.append(text)
                                for piece in _iter_text_chunks(text):
                                    yield StreamChunk(kind="content", text=piece)
                        elif dtype == "thinking_delta":
                            thinking = delta.get("thinking")
                            if isinstance(thinking, str) and thinking:
                                saw_output = True
                                aggregated_reasoning.append(thinking)
                                for piece in _iter_text_chunks(thinking):
                                    yield StreamChunk(kind="reasoning", text=piece)
                        elif dtype == "input_json_delta":
                            raise _tools_unsupported(detail="stream input_json_delta")
                        continue
                    if etype == "message_delta":
                        usage = data.get("usage")
                        if isinstance(usage, dict):
                            terminal_usage = usage
                        continue

            _ = decode_usage(terminal_usage)
            _log.set_response(
                body={
                    "_aggregated": True,
                    "content": "".join(aggregated_content),
                    "reasoning_content": "".join(aggregated_reasoning) or None,
                    "usage": terminal_usage,
                }
            )
            if not saw_output:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="anthropic stream produced no content/thinking deltas",
                )
            yield StreamChunk(kind="finish", tool_calls=None)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.anthropic_messages.stream",
            default_code="provider_request_failed",
            default_message="Anthropic 流式请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


class AnthropicMessagesAdapter:
    """ProviderAdapter for Anthropic Messages (no tools / cache off in 5B)."""

    provider = _PROVIDER
    protocol = _PROTOCOL

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        if not (base_url or "").strip():
            raise AppError(
                code="config_missing",
                message="API 基础地址未配置",
                source="llm.anthropic_messages",
                status_code=400,
                suggested_action="在 API 预设中填写 Anthropic Base URL 后重试",
                provider=self.provider,
                protocol=self.protocol,
            )
        if not (api_key or "").strip():
            raise AppError(
                code="config_missing",
                message="API Key 未配置",
                source="llm.anthropic_messages",
                status_code=400,
                suggested_action="在 API 预设中填写 Anthropic API Key 后重试",
                provider=self.provider,
                protocol=self.protocol,
            )

    def build_request(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> WireRequest:
        if not isinstance(config, GenerationConfig):
            raise TypeError("config must be GenerationConfig")
        self.validate_config(base_url=base_url, api_key=api_key)
        _reject_tools_in_config(config)
        url = _messages_url(base_url)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **_auth_headers(api_key),
        }
        payload = _build_payload(
            model=config.model,
            messages=messages,
            stream=bool(config.stream),
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
            extra_body=config.extra_body,
        )
        return WireRequest(method="POST", url=url, headers=headers, json_body=payload)

    async def list_models(self, *, base_url: str, api_key: str) -> list[str]:
        self.validate_config(base_url=base_url, api_key=api_key)
        return await list_models_anthropic(base_url=base_url, api_key=api_key)

    async def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
        as_message: bool = False,
    ) -> Any:
        if not isinstance(config, GenerationConfig):
            raise TypeError("config must be GenerationConfig")
        self.validate_config(base_url=base_url, api_key=api_key)
        return await complete_anthropic(
            base_url=base_url,
            api_key=api_key,
            messages=messages,
            config=config,
            as_message=as_message,
        )

    async def stream(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> AsyncIterator[StreamChunk]:
        if not isinstance(config, GenerationConfig):
            raise TypeError("config must be GenerationConfig")
        self.validate_config(base_url=base_url, api_key=api_key)
        async for chunk in stream_anthropic(
            base_url=base_url,
            api_key=api_key,
            messages=messages,
            config=config,
        ):
            yield chunk

    def decode_usage(self, raw: dict[str, Any] | None) -> Usage | None:
        return decode_usage(raw)
