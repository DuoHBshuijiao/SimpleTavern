"""
OpenAI Responses API provider adapter (T-805-5D).

Scope for 5D:
- non-stream + stream text paths via /v1/responses typed SSE
- reasoning_summary → StreamChunk(kind='reasoning')
- tools / built-in web_search / function_call → provider_capability_unsupported (T-806)
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
    OPENAI_RESPONSES_PROTOCOL,
    GenerationConfig,
    Usage,
    WireRequest,
)
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound

_PROVIDER = "openai"
_PROTOCOL = OPENAI_RESPONSES_PROTOCOL
_DEFAULT_MAX_TOKENS = 4096
_MAX_ERROR_BODY_CHARS = 12000
_RESPONSES_SUFFIX = "/responses"

_APP_REFERER = "https://github.com/DuoHBshuijiao/SimpleTavern"
_APP_TITLE = "SimpleTavern"


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
        source="llm.openai_responses",
        status_code=status_code,
        retryable=retryable,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="检查 OpenAI Responses 预设（Base URL / API Key / 模型）与协议是否匹配",
    )


def _tools_unsupported(*, detail: str) -> AppError:
    return AppError(
        code="provider_capability_unsupported",
        message="当前 OpenAI Responses 适配器尚未支持工具调用",
        detail=detail,
        source="llm.openai_responses",
        status_code=400,
        retryable=False,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="请改用 OpenAI Compatible Chat，或等待 T-806 工具/内建 web_search 支持",
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
            code = err.get("code") or err.get("type")
            return f"{m.strip()}" + (f" ({code})" if code else "")
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


def _responses_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("API 基础地址未配置或为空。请填写 OpenAI Base URL（如 https://api.openai.com）。")
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    lower = raw.lower()
    if lower.endswith(_RESPONSES_SUFFIX) or lower.endswith(_RESPONSES_SUFFIX + "/"):
        return raw.rstrip("/")
    # If user pasted chat/completions, strip to base then append /responses.
    if "/chat/completions" in lower:
        idx = lower.rfind("/chat/completions")
        raw = raw[:idx].rstrip("/")
    return _normalize_base_url(raw) + _RESPONSES_SUFFIX


def _models_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("API 基础地址未配置或为空。")
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    lower = raw.lower()
    for suffix in (_RESPONSES_SUFFIX, "/chat/completions"):
        if suffix in lower:
            idx = lower.rfind(suffix)
            raw = raw[:idx].rstrip("/")
            break
    return _normalize_base_url(raw) + "/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "HTTP-Referer": _APP_REFERER,
        "X-Title": _APP_TITLE,
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
                typ = item.get("type")
                if typ in {None, "text", "input_text", "output_text"} and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
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
    if extra.get("tools") is not None or extra.get("tool_choice") is not None:
        raise _tools_unsupported(detail="extra_body contains tools/tool_choice")


def _convert_input(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    _reject_tools_in_messages(messages)
    instructions_parts: list[str] = []
    items: list[dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").strip()
        content = msg.get("content")
        if role == "system":
            text = _content_to_text(content).strip()
            if text:
                instructions_parts.append(text)
            continue
        if role not in {"user", "assistant", "developer"}:
            raise _protocol_error(
                code="provider_request_invalid",
                message="消息角色不被 OpenAI Responses 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
        text = _content_to_text(content)
        # Simple role/content form accepted by Responses API.
        items.append({"role": role if role != "developer" else "developer", "content": text})

    instructions = "\n\n".join(instructions_parts) if instructions_parts else None
    return instructions, items


def _sanitize_extra_body(extra_body: dict[str, Any] | None) -> dict[str, Any]:
    if not extra_body:
        return {}
    out: dict[str, Any] = {}
    effort = None
    if isinstance(extra_body.get("reasoning"), dict):
        effort = extra_body["reasoning"].get("effort")
    if effort is None:
        effort = extra_body.get("reasoning_effort")
    thinking = extra_body.get("thinking")
    thinking_enabled = isinstance(thinking, dict) and thinking.get("type") == "enabled"
    if thinking_enabled or (isinstance(effort, str) and effort and effort != "none"):
        reasoning: dict[str, Any] = {}
        if isinstance(effort, str) and effort and effort != "none":
            reasoning["effort"] = effort
        else:
            reasoning["effort"] = "medium"
        reasoning["summary"] = "auto"
        out["reasoning"] = reasoning

    for key, value in extra_body.items():
        if key in {
            "thinking",
            "reasoning",
            "reasoning_effort",
            "tools",
            "tool_choice",
            "input",
            "instructions",
            "messages",
            "max_tokens",
            "max_completion_tokens",
        }:
            continue
        out[key] = value
    return out


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
    instructions, input_items = _convert_input(messages)
    if not input_items:
        raise _protocol_error(
            code="provider_request_invalid",
            message="没有可发送给 Responses API 的对话消息",
            detail="input empty after system extraction",
            status_code=400,
        )

    payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "stream": stream,
        # Avoid remote persistence of chat transcripts by default.
        "store": False,
    }
    if instructions:
        payload["instructions"] = instructions
    if max_tokens and max_tokens > 0:
        payload["max_output_tokens"] = int(max_tokens)
    else:
        payload["max_output_tokens"] = _DEFAULT_MAX_TOKENS
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p

    extra = _sanitize_extra_body(extra_body)
    # If reasoning effort is set, Responses often expects temperature omitted/1.
    if "reasoning" in extra and temperature is not None:
        payload.pop("temperature", None)
    payload.update(extra)
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


def _extract_text_and_reasoning(data: dict[str, Any]) -> tuple[str, str | None]:
    # Prefer convenience field when present.
    convenience = data.get("output_text")
    texts: list[str] = []
    reasonings: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ in {"function_call", "custom_tool_call", "web_search_call", "file_search_call", "computer_call"}:
                raise _tools_unsupported(detail=f"response output item type={typ}")
            if typ == "reasoning":
                summary = item.get("summary")
                if isinstance(summary, list):
                    for part in summary:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            reasonings.append(part["text"])
                continue
            if typ == "message":
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                            texts.append(part["text"])
                continue
    text = "".join(texts)
    if not text and isinstance(convenience, str):
        text = convenience
    reasoning = "".join(reasonings).strip() or None
    return text, reasoning


def _iter_text_chunks(text: str) -> list[str]:
    if not text:
        return []
    size = max(1, STREAM_TEXT_CHUNK_SIZE)
    return [text[i : i + size] for i in range(0, len(text), size)]


def decode_usage(raw: dict[str, Any] | None) -> Usage | None:
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
    total = _as_int(raw.get("total_tokens"))
    details = raw.get("output_tokens_details")
    reasoning = None
    if isinstance(details, dict):
        reasoning = _as_int(details.get("reasoning_tokens"))
    input_details = raw.get("input_tokens_details")
    cache_read = None
    if isinstance(input_details, dict):
        cache_read = _as_int(input_details.get("cached_tokens"))
    if input_tokens is None and output_tokens is None and total is None:
        return None
    if total is None and (input_tokens is not None or output_tokens is not None):
        total = (input_tokens or 0) + (output_tokens or 0)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cache_read_input_tokens=cache_read,
        cache_write_input_tokens=None,
        reasoning_tokens=reasoning,
        raw=dict(raw),
    )


async def list_models_responses(*, base_url: str, api_key: str) -> list[str]:
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
            data = _decode_json_object(r, context="openai models")
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
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
                    out.append(item["id"].strip())
            return sorted(set(out))
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.openai_responses.models",
            default_code="provider_request_failed",
            default_message="获取 OpenAI 模型列表失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def complete_responses(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
    as_message: bool = False,
) -> ChatCompletionResult | ChatCompletionMessage:
    _reject_tools_in_config(config)
    url = _responses_url(base_url)
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
            data = _decode_json_object(r, context="openai responses")
            _log.set_response(body=data)
            text, reasoning = _extract_text_and_reasoning(data)
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
                    detail="openai responses: empty output_text and reasoning summary",
                )
            return ChatCompletionResult(text=text)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.openai_responses",
            default_code="provider_request_failed",
            default_message="OpenAI Responses 请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


_TOOLISH_EVENT_TYPES = frozenset(
    {
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.output_item.added",
        "response.web_search_call.in_progress",
        "response.web_search_call.searching",
        "response.web_search_call.completed",
        "response.file_search_call.in_progress",
        "response.file_search_call.searching",
        "response.file_search_call.completed",
        "response.custom_tool_call_input.delta",
        "response.custom_tool_call_input.done",
    }
)


async def stream_responses(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
) -> AsyncIterator[StreamChunk]:
    _reject_tools_in_config(config)
    url = _responses_url(base_url)
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
    completed = False

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
                    if not data_str or data_str == "[DONE]":
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
                    if etype in {"response.created", "response.in_progress", "response.output_text.done"}:
                        continue
                    if etype == "error" or data.get("type") == "error":
                        err = data.get("error") if isinstance(data.get("error"), dict) else data
                        msg = ""
                        if isinstance(err, dict):
                            msg = str(err.get("message") or err.get("code") or "")
                        raise _protocol_error(
                            code="provider_request_failed",
                            message="OpenAI Responses 流式返回错误",
                            detail=msg or data_str[:500],
                            retryable=True,
                        )
                    if etype in _TOOLISH_EVENT_TYPES:
                        # output_item.added may be message/reasoning — only fail on toolish items.
                        if etype == "response.output_item.added":
                            item = data.get("item")
                            if isinstance(item, dict):
                                item_type = item.get("type")
                                if item_type in {
                                    "function_call",
                                    "web_search_call",
                                    "file_search_call",
                                    "computer_call",
                                    "custom_tool_call",
                                }:
                                    raise _tools_unsupported(detail=f"stream output_item type={item_type}")
                            continue
                        raise _tools_unsupported(detail=f"stream event type={etype}")
                    if etype == "response.output_text.delta":
                        delta = data.get("delta")
                        if isinstance(delta, str) and delta:
                            saw_output = True
                            aggregated_content.append(delta)
                            for piece in _iter_text_chunks(delta):
                                yield StreamChunk(kind="content", text=piece)
                        continue
                    if etype == "response.reasoning_summary_text.delta":
                        delta = data.get("delta")
                        if isinstance(delta, str) and delta:
                            saw_output = True
                            aggregated_reasoning.append(delta)
                            for piece in _iter_text_chunks(delta):
                                yield StreamChunk(kind="reasoning", text=piece)
                        continue
                    if etype == "response.completed":
                        completed = True
                        resp = data.get("response")
                        if isinstance(resp, dict) and isinstance(resp.get("usage"), dict):
                            terminal_usage = resp["usage"]
                        elif isinstance(data.get("usage"), dict):
                            terminal_usage = data["usage"]
                        continue

            _ = decode_usage(terminal_usage)
            _log.set_response(
                body={
                    "_aggregated": True,
                    "content": "".join(aggregated_content),
                    "reasoning_content": "".join(aggregated_reasoning) or None,
                    "usage": terminal_usage,
                    "completed": completed,
                }
            )
            if not saw_output:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="openai responses stream produced no output_text/reasoning deltas",
                )
            yield StreamChunk(kind="finish", tool_calls=None)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.openai_responses.stream",
            default_code="provider_request_failed",
            default_message="OpenAI Responses 流式请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


class OpenAIResponsesAdapter:
    """ProviderAdapter for OpenAI Responses (no tools in 5D)."""

    provider = _PROVIDER
    protocol = _PROTOCOL

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        if not (base_url or "").strip():
            raise AppError(
                code="config_missing",
                message="API 基础地址未配置",
                source="llm.openai_responses",
                status_code=400,
                suggested_action="在 API 预设中填写 Base URL（如 https://api.openai.com）后重试",
                provider=self.provider,
                protocol=self.protocol,
            )
        if not (api_key or "").strip():
            raise AppError(
                code="config_missing",
                message="API Key 未配置",
                source="llm.openai_responses",
                status_code=400,
                suggested_action="在 API 预设中填写 API Key 后重试",
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
        url = _responses_url(base_url)
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
        return await list_models_responses(base_url=base_url, api_key=api_key)

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
        return await complete_responses(
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
        async for chunk in stream_responses(
            base_url=base_url,
            api_key=api_key,
            messages=messages,
            config=config,
        ):
            yield chunk

    def decode_usage(self, raw: dict[str, Any] | None) -> Usage | None:
        return decode_usage(raw)
