"""
Anthropic Messages API provider adapter (T-805-5B / T-806-6A / T-806-6B).

Scope:
- non-stream + stream text (and thinking→reasoning) paths
- tools round-trip: OpenAI-shaped tools ↔ Anthropic tool_use/tool_result (T-806-6B)
- prompt cache: anthropic_prompt_cache off|5m|1h on system block only (T-806-6A)
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
    normalize_anthropic_prompt_cache,
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


def _as_content_blocks(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return list(content)
    if isinstance(content, str) and content:
        return [{"type": "text", "text": content}]
    return []


def _merge_same_role_content(
    prev: str | list[dict[str, Any]],
    new: str | list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    if isinstance(prev, str) and isinstance(new, str):
        return prev + "\n" + new
    return _as_content_blocks(prev) + _as_content_blocks(new)


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _arguments_to_json_string(inp: Any) -> str:
    if isinstance(inp, str):
        return inp if inp.strip() else "{}"
    if isinstance(inp, dict):
        return json.dumps(inp, ensure_ascii=False)
    return "{}"


def _convert_tools_openai_to_anthropic(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """OpenAI tools → Anthropic tools (name / description / input_schema)."""
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if isinstance(tool.get("name"), str) and isinstance(tool.get("input_schema"), dict):
            entry: dict[str, Any] = {
                "name": tool["name"].strip(),
                "input_schema": tool["input_schema"],
            }
            desc = tool.get("description")
            if isinstance(desc, str) and desc:
                entry["description"] = desc
            if entry["name"]:
                out.append(entry)
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if fn is None and tool.get("type") != "function":
            # Allow bare {name, description, parameters} shapes.
            fn = tool if isinstance(tool.get("name"), str) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        params = fn.get("parameters")
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        entry = {
            "name": name.strip(),
            "input_schema": params,
        }
        desc = fn.get("description")
        if isinstance(desc, str) and desc:
            entry["description"] = desc
        out.append(entry)
    return out or None


def _convert_tool_choice(tool_choice: Any) -> dict[str, Any] | None:
    """Map OpenAI tool_choice → Anthropic tool_choice."""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        low = tool_choice.strip().lower()
        if low == "auto":
            return {"type": "auto"}
        if low == "none":
            return {"type": "none"}
        if low in {"required", "any"}:
            return {"type": "any"}
        return None
    if isinstance(tool_choice, dict):
        typ = tool_choice.get("type")
        if typ == "function":
            fn = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
            name = fn.get("name") if isinstance(fn.get("name"), str) else tool_choice.get("name")
            if isinstance(name, str) and name.strip():
                return {"type": "tool", "name": name.strip()}
            return None
        if typ == "tool":
            name = tool_choice.get("name")
            if isinstance(name, str) and name.strip():
                return {"type": "tool", "name": name.strip()}
            return None
        if typ in {"auto", "none", "any"}:
            return {"type": typ}
    return None


def _assistant_tool_use_blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = msg.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    blocks: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = fn.get("name") if isinstance(fn.get("name"), str) else ""
        if not name.strip():
            continue
        blocks.append(
            {
                "type": "tool_use",
                "id": str(tc.get("id") or ""),
                "name": name.strip(),
                "input": _parse_tool_arguments(fn.get("arguments")),
            }
        )
    return blocks


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    i = 0
    n = len(messages)

    while i < n:
        msg = messages[i]
        if not isinstance(msg, dict):
            i += 1
            continue
        role = (msg.get("role") or "").strip()
        content = msg.get("content")

        if role == "system":
            text = _content_to_text(content).strip()
            if text:
                system_parts.append(text)
            i += 1
            continue

        if role == "tool":
            # Consecutive role=tool → single user message with tool_result blocks.
            tool_results: list[dict[str, Any]] = []
            while i < n:
                m = messages[i]
                if not isinstance(m, dict) or (m.get("role") or "").strip() != "tool":
                    break
                tool_call_id = m.get("tool_call_id")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(tool_call_id or ""),
                        "content": _content_to_text(m.get("content")),
                    }
                )
                i += 1
            if converted and converted[-1]["role"] == "user":
                converted[-1] = {
                    "role": "user",
                    "content": _merge_same_role_content(converted[-1]["content"], tool_results),
                }
            else:
                converted.append({"role": "user", "content": tool_results})
            continue

        if role == "assistant":
            tool_blocks = _assistant_tool_use_blocks(msg)
            text_content = _to_anthropic_content(content)
            if tool_blocks:
                blocks = _as_content_blocks(text_content) + tool_blocks
                anth_content: str | list[dict[str, Any]] = blocks
            else:
                anth_content = text_content
            if converted and converted[-1]["role"] == "assistant":
                converted[-1] = {
                    "role": "assistant",
                    "content": _merge_same_role_content(converted[-1]["content"], anth_content),
                }
            else:
                converted.append({"role": "assistant", "content": anth_content})
            i += 1
            continue

        if role == "user":
            anth_content = _to_anthropic_content(content)
            if converted and converted[-1]["role"] == "user":
                converted[-1] = {
                    "role": "user",
                    "content": _merge_same_role_content(converted[-1]["content"], anth_content),
                }
            else:
                converted.append({"role": "user", "content": anth_content})
            i += 1
            continue

        raise _protocol_error(
            code="provider_request_invalid",
            message="消息角色不被 Anthropic Messages 支持",
            detail=f"unsupported role={role!r}",
            status_code=400,
        )

    if converted and converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": "."})

    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _sanitize_extra_body(extra_body: dict[str, Any] | None) -> tuple[dict[str, Any], bool, str]:
    """
    Map shared reasoning extra_body into Anthropic thinking; strip OpenAI-only keys.
    Returns (payload_fragment, thinking_enabled, anthropic_prompt_cache).
    """
    if not extra_body:
        return {}, False, "off"
    out: dict[str, Any] = {}
    thinking_enabled = False
    cache = normalize_anthropic_prompt_cache(extra_body.get("anthropic_prompt_cache"))

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

    # Pass through Anthropic-native keys if callers set them explicitly.
    # cache_control / anthropic_prompt_cache are handled separately on system.
    # tools / tool_choice are handled in _build_payload.
    for key, value in extra_body.items():
        if key in {
            "thinking",
            "reasoning",
            "reasoning_effort",
            "tools",
            "tool_choice",
            "cache_control",
            "anthropic_prompt_cache",
        }:
            continue
        if key == "system":
            continue
        out[key] = value

    return out, thinking_enabled, cache


def _system_with_cache(system: str | None, cache: str) -> str | list[dict[str, Any]] | None:
    """Apply Anthropic prompt cache to the stable system block only (T-806-6A)."""
    if not system:
        return None
    if cache == "off":
        return system
    control: dict[str, Any] = {"type": "ephemeral"}
    if cache == "1h":
        control["ttl"] = "1h"
    elif cache == "5m":
        control["ttl"] = "5m"
    return [{"type": "text", "text": system, "cache_control": control}]


def _resolve_tools_and_choice(
    *,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any | None,
    extra_body: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    resolved_tools = tools
    resolved_choice = tool_choice
    if extra_body:
        if resolved_tools is None and extra_body.get("tools") is not None:
            raw = extra_body.get("tools")
            resolved_tools = raw if isinstance(raw, list) else None
        if resolved_choice is None and extra_body.get("tool_choice") is not None:
            resolved_choice = extra_body.get("tool_choice")
    anth_tools = _convert_tools_openai_to_anthropic(resolved_tools)
    anth_choice = _convert_tool_choice(resolved_choice)
    return anth_tools, anth_choice


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
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    system, anth_messages = _convert_messages(messages)
    if not anth_messages:
        raise _protocol_error(
            code="provider_request_invalid",
            message="没有可发送给 Anthropic 的对话消息",
            detail="messages empty after system extraction",
            status_code=400,
        )

    extra, thinking_enabled, cache = _sanitize_extra_body(extra_body)
    payload: dict[str, Any] = {
        "model": model,
        "messages": anth_messages,
        "max_tokens": int(max_tokens) if max_tokens and max_tokens > 0 else _DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    system_payload = _system_with_cache(system, cache)
    if system_payload is not None:
        payload["system"] = system_payload
    if thinking_enabled:
        # Anthropic requires temperature=1 (or omit) when thinking is enabled.
        payload["temperature"] = 1
    elif temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None and not thinking_enabled:
        payload["top_p"] = top_p

    anth_tools, anth_choice = _resolve_tools_and_choice(
        tools=tools,
        tool_choice=tool_choice,
        extra_body=extra_body,
    )
    if anth_tools is not None:
        payload["tools"] = anth_tools
    if anth_choice is not None:
        payload["tool_choice"] = anth_choice

    payload.update(extra)
    # Top-level cache_control is not used for 6A (system-block only).
    payload.pop("cache_control", None)
    payload.pop("anthropic_prompt_cache", None)
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


def _extract_text_thinking_and_tools(
    content_blocks: Any,
) -> tuple[str, str | None, list[dict[str, Any]] | None]:
    texts: list[str] = []
    thinking: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    if not isinstance(content_blocks, list):
        return "", None, None
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        typ = block.get("type")
        if typ == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif typ == "thinking" and isinstance(block.get("thinking"), str):
            thinking.append(block["thinking"])
        elif typ == "tool_use":
            name = block.get("name") if isinstance(block.get("name"), str) else ""
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": _arguments_to_json_string(block.get("input")),
                    },
                }
            )
    text = "".join(texts)
    reasoning = "".join(thinking).strip() or None
    return text, reasoning, tool_calls or None


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
            data = _decode_json_object(r, context="anthropic messages")
            _log.set_response(body=data)
            text, reasoning, tool_calls = _extract_text_thinking_and_tools(data.get("content"))
            # Terminal usage for future T-807.
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
                    detail="anthropic messages: empty text, thinking and tool_calls",
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
        tools=config.tools,
        tool_choice=config.tool_choice,
    )

    saw_output = False
    terminal_usage: dict[str, Any] | None = None
    # index → {id, name, arguments_acc}
    pending_tools: dict[int, dict[str, str]] = {}

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
                            idx_raw = data.get("index")
                            idx = idx_raw if isinstance(idx_raw, int) else len(pending_tools)
                            pending_tools[idx] = {
                                "id": str(block.get("id") or ""),
                                "name": str(block.get("name") or ""),
                                "arguments_acc": "",
                            }
                            saw_output = True
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
                            idx_raw = data.get("index")
                            idx = idx_raw if isinstance(idx_raw, int) else None
                            partial = delta.get("partial_json")
                            if idx is not None and idx in pending_tools and isinstance(partial, str):
                                pending_tools[idx]["arguments_acc"] += partial
                                saw_output = True
                        continue
                    if etype == "message_delta":
                        usage = data.get("usage")
                        if isinstance(usage, dict):
                            terminal_usage = usage
                        continue

            sorted_tool_calls: list[dict[str, Any]] | None = None
            if pending_tools:
                sorted_tool_calls = []
                for idx in sorted(pending_tools.keys()):
                    t = pending_tools[idx]
                    args = t["arguments_acc"] if t["arguments_acc"].strip() else "{}"
                    sorted_tool_calls.append(
                        {
                            "id": t["id"],
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "arguments": args,
                            },
                        }
                    )

            _ = decode_usage(terminal_usage)
            body: dict[str, Any] = {
                "_aggregated": True,
                "content": "".join(aggregated_content),
                "reasoning_content": "".join(aggregated_reasoning) or None,
                "usage": terminal_usage,
            }
            if sorted_tool_calls:
                body["tool_calls"] = sorted_tool_calls
            _log.set_response(body=body)
            if not saw_output:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="anthropic stream produced no content/thinking/tool deltas",
                )
            yield StreamChunk(kind="finish", tool_calls=sorted_tool_calls)
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
    """ProviderAdapter for Anthropic Messages (tools + prompt cache)."""

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
            tools=config.tools,
            tool_choice=config.tool_choice,
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
