"""
OpenAI Responses API provider adapter (T-805-5D / T-806-6B).

Supports:
- non-stream + stream text paths via /v1/responses typed SSE
- reasoning_summary → StreamChunk(kind='reasoning')
- function tools round-trip (Chat tools/messages ↔ Responses tools/items)
- built-in web_search / hosted tools → provider_capability_unsupported (T-806-6C)
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

# Hosted / built-in Responses tool types (not app-defined function tools).
_BUILTIN_TOOL_TYPES = frozenset(
    {
        "web_search",
        "web_search_preview",
        "file_search",
        "computer_use_preview",
        "computer",
        "code_interpreter",
        "image_generation",
        "mcp",
        "custom",
    }
)

_BUILTIN_OUTPUT_ITEM_TYPES = frozenset(
    {
        "web_search_call",
        "file_search_call",
        "computer_call",
        "custom_tool_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
    }
)


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
        message="当前 OpenAI Responses 适配器尚未支持该工具能力",
        detail=detail,
        source="llm.openai_responses",
        status_code=400,
        retryable=False,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="请改用 function tools，或等待 T-806-6C 内建 web_search 支持",
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


def _arguments_to_str(arguments: Any) -> str:
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return "{}"
    try:
        return json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(arguments)


def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """OpenAI Chat Completions tools → Responses function tools."""
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise _protocol_error(
                code="provider_request_invalid",
                message="tools 项必须是对象",
                detail=f"tools[{idx}] is {type(tool).__name__}",
                status_code=400,
            )
        typ = tool.get("type")
        if isinstance(typ, str) and typ in _BUILTIN_TOOL_TYPES:
            raise _tools_unsupported(detail=f"built-in tool type={typ!r} (T-806-6C)")
        if typ and typ != "function":
            raise _tools_unsupported(detail=f"unsupported tool type={typ!r}")

        # Chat nested: {type:function, function:{name,description,parameters}}
        nested = tool.get("function")
        if isinstance(nested, dict):
            name = nested.get("name")
            if not isinstance(name, str) or not name.strip():
                raise _protocol_error(
                    code="provider_request_invalid",
                    message="function tool 缺少 name",
                    detail=f"tools[{idx}].function.name missing",
                    status_code=400,
                )
            item: dict[str, Any] = {
                "type": "function",
                "name": name.strip(),
                "description": nested.get("description") if isinstance(nested.get("description"), str) else "",
                "parameters": nested.get("parameters")
                if isinstance(nested.get("parameters"), dict)
                else {"type": "object", "properties": {}},
            }
            strict = nested.get("strict") if "strict" in nested else tool.get("strict")
            if isinstance(strict, bool):
                item["strict"] = strict
            out.append(item)
            continue

        # Already Responses-shaped: {type:function, name, parameters, ...}
        name = tool.get("name")
        if isinstance(name, str) and name.strip():
            item = {
                "type": "function",
                "name": name.strip(),
                "description": tool.get("description") if isinstance(tool.get("description"), str) else "",
                "parameters": tool.get("parameters")
                if isinstance(tool.get("parameters"), dict)
                else {"type": "object", "properties": {}},
            }
            if isinstance(tool.get("strict"), bool):
                item["strict"] = tool["strict"]
            out.append(item)
            continue

        raise _protocol_error(
            code="provider_request_invalid",
            message="无法识别的 function tool 定义",
            detail=f"tools[{idx}] missing function.name",
            status_code=400,
        )
    return out or None


def _convert_tool_choice(tool_choice: Any) -> Any:
    """Map Chat tool_choice to Responses tool_choice when needed."""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    if not isinstance(tool_choice, dict):
        return tool_choice
    typ = tool_choice.get("type")
    if typ == "function":
        if isinstance(tool_choice.get("name"), str) and tool_choice["name"].strip():
            return {"type": "function", "name": tool_choice["name"].strip()}
        nested = tool_choice.get("function")
        if isinstance(nested, dict) and isinstance(nested.get("name"), str) and nested["name"].strip():
            return {"type": "function", "name": nested["name"].strip()}
    return tool_choice


def _function_call_to_chat_tool_call(item: dict[str, Any]) -> dict[str, Any]:
    call_id = item.get("call_id") or item.get("id") or ""
    name = item.get("name") if isinstance(item.get("name"), str) else ""
    return {
        "id": call_id if isinstance(call_id, str) else str(call_id),
        "type": "function",
        "function": {
            "name": name,
            "arguments": _arguments_to_str(item.get("arguments")),
        },
    }


def _convert_input(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
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

        if role == "tool":
            call_id = msg.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise _protocol_error(
                    code="provider_request_invalid",
                    message="tool 消息缺少 tool_call_id",
                    detail="role=tool requires tool_call_id",
                    status_code=400,
                )
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id.strip(),
                    "output": _content_to_text(content),
                }
            )
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            text = _content_to_text(content)
            if isinstance(tool_calls, list) and tool_calls:
                if text.strip():
                    items.append({"role": "assistant", "content": text})
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    call_id = tc.get("id")
                    name = fn.get("name") if isinstance(fn.get("name"), str) else ""
                    if not isinstance(call_id, str) or not call_id.strip():
                        raise _protocol_error(
                            code="provider_request_invalid",
                            message="assistant.tool_calls 缺少 id",
                            detail="tool_calls[].id is required for Responses function_call",
                            status_code=400,
                        )
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call_id.strip(),
                            "name": name,
                            "arguments": _arguments_to_str(fn.get("arguments")),
                        }
                    )
                continue
            items.append({"role": "assistant", "content": text})
            continue

        if role not in {"user", "developer"}:
            raise _protocol_error(
                code="provider_request_invalid",
                message="消息角色不被 OpenAI Responses 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
        items.append({"role": role, "content": _content_to_text(content)})

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


def _resolve_tools_and_choice(
    *,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    extra_body: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]] | None, Any]:
    extra = extra_body or {}
    resolved_tools = tools if tools is not None else extra.get("tools")
    if resolved_tools is not None and not isinstance(resolved_tools, list):
        raise _protocol_error(
            code="provider_request_invalid",
            message="tools 必须是数组",
            detail=f"got {type(resolved_tools).__name__}",
            status_code=400,
        )
    resolved_choice = tool_choice if tool_choice is not None else extra.get("tool_choice")
    return _convert_tools(resolved_tools), _convert_tool_choice(resolved_choice)


def _build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    extra_body: dict[str, Any] | None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
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

    converted_tools, converted_choice = _resolve_tools_and_choice(
        tools=tools,
        tool_choice=tool_choice,
        extra_body=extra_body,
    )
    if converted_tools is not None:
        payload["tools"] = converted_tools
    if converted_choice is not None:
        payload["tool_choice"] = converted_choice

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


def _extract_output(data: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]] | None]:
    convenience = data.get("output_text")
    texts: list[str] = []
    reasonings: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ in _BUILTIN_OUTPUT_ITEM_TYPES:
                raise _tools_unsupported(detail=f"response output item type={typ}")
            if typ == "function_call":
                tool_calls.append(_function_call_to_chat_tool_call(item))
                continue
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
    return text, reasoning, (tool_calls or None)


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
        tools=config.tools,
        tool_choice=config.tool_choice,
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
            text, reasoning, tool_calls = _extract_output(data)
            _ = decode_usage(data.get("usage") if isinstance(data.get("usage"), dict) else None)
            if as_message:
                return ChatCompletionMessage(
                    role="assistant",
                    content=text,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls,
                )
            if not text.strip() and not reasoning and not tool_calls:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游服务未返回有效文本",
                    detail="openai responses: empty output_text, reasoning summary, and tool_calls",
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


_BUILTIN_STREAM_EVENT_TYPES = frozenset(
    {
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
        tools=config.tools,
        tool_choice=config.tool_choice,
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
            # item_id (fc_*) → Chat-shaped tool_call; preserve insertion order
            tool_calls_by_item: dict[str, dict[str, Any]] = {}
            tool_call_order: list[str] = []
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
                    if etype in {
                        "response.created",
                        "response.in_progress",
                        "response.output_text.done",
                        "response.output_item.done",
                    }:
                        # output_item.done may carry final function_call; sync if present.
                        if etype == "response.output_item.done":
                            item = data.get("item")
                            if isinstance(item, dict) and item.get("type") == "function_call":
                                item_id = item.get("id")
                                key = item_id if isinstance(item_id, str) and item_id else f"idx-{data.get('output_index')}"
                                chat_tc = _function_call_to_chat_tool_call(item)
                                if key not in tool_calls_by_item:
                                    tool_call_order.append(key)
                                tool_calls_by_item[key] = chat_tc
                                saw_output = True
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
                    if etype in _BUILTIN_STREAM_EVENT_TYPES:
                        raise _tools_unsupported(detail=f"stream event type={etype}")
                    if etype == "response.output_item.added":
                        item = data.get("item")
                        if isinstance(item, dict):
                            item_type = item.get("type")
                            if item_type in _BUILTIN_OUTPUT_ITEM_TYPES:
                                raise _tools_unsupported(detail=f"stream output_item type={item_type}")
                            if item_type == "function_call":
                                item_id = item.get("id")
                                key = (
                                    item_id
                                    if isinstance(item_id, str) and item_id
                                    else f"idx-{data.get('output_index')}"
                                )
                                chat_tc = _function_call_to_chat_tool_call(item)
                                if key not in tool_calls_by_item:
                                    tool_call_order.append(key)
                                tool_calls_by_item[key] = chat_tc
                                saw_output = True
                        continue
                    if etype == "response.function_call_arguments.delta":
                        item_id = data.get("item_id")
                        delta = data.get("delta")
                        key = item_id if isinstance(item_id, str) and item_id else None
                        if key and key in tool_calls_by_item and isinstance(delta, str) and delta:
                            tool_calls_by_item[key]["function"]["arguments"] += delta
                            saw_output = True
                        continue
                    if etype == "response.function_call_arguments.done":
                        item_id = data.get("item_id")
                        arguments = data.get("arguments")
                        key = item_id if isinstance(item_id, str) and item_id else None
                        if key and key in tool_calls_by_item and isinstance(arguments, str):
                            tool_calls_by_item[key]["function"]["arguments"] = arguments
                            saw_output = True
                        continue
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

            sorted_tool_calls = (
                [tool_calls_by_item[k] for k in tool_call_order] if tool_call_order else None
            )
            _ = decode_usage(terminal_usage)
            body: dict[str, Any] = {
                "_aggregated": True,
                "content": "".join(aggregated_content),
                "reasoning_content": "".join(aggregated_reasoning) or None,
                "usage": terminal_usage,
                "completed": completed,
            }
            if sorted_tool_calls:
                body["tool_calls"] = sorted_tool_calls
            _log.set_response(body=body)
            if not saw_output:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="openai responses stream produced no output_text/reasoning/function_call",
                )
            yield StreamChunk(kind="finish", tool_calls=sorted_tool_calls)
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
    """ProviderAdapter for OpenAI Responses (function tools in T-806-6B)."""

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
            tools=config.tools,
            tool_choice=config.tool_choice,
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
