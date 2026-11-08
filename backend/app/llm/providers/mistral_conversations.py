"""Mistral Conversations API 适配器（T-832）。

依据 https://docs.mistral.ai/api/endpoint/beta/conversations 和 https://docs.mistral.ai/openapi.yaml 的
ConversationRequest / ConversationResponse / ConversationEvents schema，
以及 https://docs.mistral.ai/inference/conversations/reasoning 。

每次都把完整历史放进 ``inputs``，``store=false``，不使用服务端保存的会话。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import httpx

from app.errors import AppError, as_app_error
from app.llm.providers.openai_compatible_chat import (
    STREAM_TEXT_CHUNK_SIZE,
    ChatCompletionMessage,
    ChatCompletionResult,
    StreamChunk,
    _raise_http_error,
    _raise_stream_http_error,
)
from app.llm.stream_errors import stream_interrupted_error
from app.llm.types import (
    MISTRAL_CONVERSATIONS_PROTOCOL,
    GenerationConfig,
    Usage,
    WireRequest,
    auth_headers_for_style,
)
from app.llm.vertex_auth import looks_like_service_account_json
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound

_PROVIDER = "mistral"
_PROTOCOL = MISTRAL_CONVERSATIONS_PROTOCOL
_SOURCE = "llm.mistral_conversations"
_CONVERSATIONS_PATH = "/v1/conversations"
# CompletionArgs 白名单（OpenAPI additionalProperties=false）
_COMPLETION_ARG_KEYS = {
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "random_seed",
    "prediction",
    "response_format",
    "reasoning_effort",
}


def _error(
    *,
    code: str,
    message: str,
    detail: str,
    retryable: bool = False,
    status_code: int = 502,
    suggested_action: str = "检查 Mistral 预设（Base URL / API Key / 模型）与协议是否匹配",
    upstream_status: int | None = None,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        detail=detail,
        source=_SOURCE,
        status_code=status_code,
        retryable=retryable,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action=suggested_action,
        upstream_status=upstream_status,
    )


def _unsupported(message: str, detail: str, *, suggested_action: str = "换用支持该能力的模型或协议") -> AppError:
    return _error(
        code="provider_capability_unsupported",
        message=message,
        detail=detail,
        status_code=400,
        suggested_action=suggested_action,
    )


def _api_root(base_url: str) -> str:
    """去掉结尾的 /v1 或 /v1/conversations，只留 API 根。"""
    raw = (base_url or "").strip()
    if not raw:
        raise _error(code="config_missing", message="API 基础地址未配置", detail="base_url is empty", status_code=400)
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    for suffix in (_CONVERSATIONS_PATH, "/v1"):
        if urlsplit(raw).path.lower().endswith(suffix):
            return raw[: -len(suffix)]
    return raw


def _auth_headers(api_key: str, auth_style: str | None) -> dict[str, str]:
    if looks_like_service_account_json(api_key):
        raise _error(
            code="config_invalid",
            message="Mistral 预设的密钥不能是服务账号 JSON",
            detail="api key looks like a Google service account",
            status_code=400,
            suggested_action="填写 Mistral API Key",
        )
    return auth_headers_for_style(api_key, auth_style or "bearer")


def _extra_headers(config: GenerationConfig) -> dict[str, str]:
    raw = config.extra_headers
    return {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()} if raw else {}


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
                if item.get("type") in {"image_url", "input_image", "image"}:
                    raise _unsupported(
                        "当前 Mistral Conversations 适配器尚未支持图片输入",
                        f"content part type={item.get('type')}",
                        suggested_action="去掉图片后重试，或换用支持图片的协议",
                    )
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _arguments_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw if raw.strip() else "{}"
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return "{}"


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """OpenAI 形状消息 → (instructions, inputs 条目)。"""
    instructions: list[str] = []
    entries: list[dict[str, Any]] = []
    pending_reasoning = ""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip()
        if role == "system":
            text = _content_to_text(msg.get("content")).strip()
            if text:
                instructions.append(text)
        elif role == "user":
            pending_reasoning = ""
            text = _content_to_text(msg.get("content"))
            if text.strip():
                entries.append({"type": "message.input", "role": "user", "content": text})
        elif role == "tool":
            pending_reasoning = ""
            entries.append(
                {
                    "type": "function.result",
                    "tool_call_id": str(msg.get("tool_call_id") or ""),
                    "result": _content_to_text(msg.get("content")),
                }
            )
        elif role == "assistant":
            reasoning = str(msg.get("reasoning_content") or "").strip() or pending_reasoning
            text = _content_to_text(msg.get("content"))
            tool_calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
            if not text.strip() and not tool_calls:
                # 只带思考内容的占位消息：并入下一条 assistant
                pending_reasoning = reasoning
                continue
            pending_reasoning = ""
            if text.strip() or reasoning:
                content: Any = text
                if reasoning:
                    # 官方要求多轮时保留 ThinkChunk
                    content = [{"type": "thinking", "thinking": [{"type": "text", "text": reasoning}]}]
                    if text.strip():
                        content.append({"type": "text", "text": text})
                entries.append({"type": "message.output", "role": "assistant", "content": content})
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = str(fn.get("name") or "").strip()
                if name:
                    entries.append(
                        {
                            "type": "function.call",
                            "tool_call_id": str(tc.get("id") or ""),
                            "name": name,
                            "arguments": _arguments_text(fn.get("arguments")),
                        }
                    )
        else:
            raise _error(
                code="provider_request_invalid",
                message="消息角色不被 Mistral Conversations 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
    if not entries:
        raise _error(
            code="provider_request_invalid",
            message="没有可发送给 Mistral 的对话消息",
            detail="inputs empty after system extraction",
            status_code=400,
        )
    last = entries[-1]
    if last["type"] == "message.output" and isinstance(last["content"], str):
        # 末尾的 assistant 是续写前缀
        entries[-1] = {"type": "message.input", "role": "assistant", "content": last["content"], "prefix": True}
    return ("\n\n".join(instructions) if instructions else None), entries


def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        name_source = fn or tool
        if (fn is None and not isinstance(tool.get("input_schema"), dict)) or tool.get("type") not in {None, "function"}:
            raise _unsupported(
                "Mistral Conversations 不支持这种工具类型",
                f"tool type={tool.get('type')!r}",
                suggested_action="改用函数工具，或在预设中把联网来源设为独立搜索",
            )
        name = str(name_source.get("name") or "").strip()
        if not name:
            continue
        parameters = name_source.get("parameters") if fn is not None else tool.get("input_schema")
        function: dict[str, Any] = {
            "name": name,
            "parameters": parameters if isinstance(parameters, dict) else {"type": "object", "properties": {}},
        }
        if isinstance(name_source.get("description"), str) and name_source["description"]:
            function["description"] = name_source["description"]
        out.append({"type": "function", "function": function})
    return out


def _convert_tool_choice(tool_choice: Any) -> str | None:
    if tool_choice is None:
        return None
    key = tool_choice if isinstance(tool_choice, str) else None
    if isinstance(tool_choice, dict) and tool_choice.get("type") in {"auto", "none", "any", "required"}:
        key = tool_choice["type"]
    if key in {"auto", "none", "any", "required"}:
        return key
    raise _unsupported(
        "Mistral Conversations 不支持指定具体工具",
        f"tool_choice={tool_choice!r}",
        suggested_action="把工具选择改为自动",
    )


def _build_payload(*, messages: list[dict[str, Any]], config: GenerationConfig, stream: bool) -> dict[str, Any]:
    instructions, entries = _convert_messages(messages)
    extra = dict(config.extra_body or {})
    raw_tools = extra.pop("tools", None)
    raw_choice = extra.pop("tool_choice", None)
    extra.pop("anthropic_prompt_cache", None)
    leftovers = [k for k, v in extra.items() if v is not None and k not in _COMPLETION_ARG_KEYS]
    if leftovers:
        raise _unsupported("Mistral Conversations 不支持这些请求参数", "unsupported fields: " + ", ".join(sorted(leftovers)))

    completion_args: dict[str, Any] = {k: v for k, v in extra.items() if v is not None}
    if config.temperature is not None:
        completion_args["temperature"] = config.temperature
    if config.top_p is not None:
        completion_args["top_p"] = config.top_p
    if config.max_tokens and config.max_tokens > 0:
        completion_args["max_tokens"] = int(config.max_tokens)
    tools = _convert_tools(config.tools if config.tools is not None else raw_tools)
    choice = _convert_tool_choice(config.tool_choice if config.tool_choice is not None else raw_choice)
    if choice is not None:
        completion_args["tool_choice"] = choice

    payload: dict[str, Any] = {
        "model": config.model,
        "inputs": entries,
        "stream": stream,
        "store": False,
    }
    if instructions:
        payload["instructions"] = instructions
    if tools:
        payload["tools"] = tools
    if completion_args:
        payload["completion_args"] = completion_args
    return payload


def decode_usage(raw: dict[str, Any] | None) -> Usage | None:
    if not isinstance(raw, dict) or not raw:
        return None

    def as_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    prompt = as_int(raw.get("prompt_tokens"))
    completion = as_int(raw.get("completion_tokens"))
    total = as_int(raw.get("total_tokens"))
    if prompt is None and completion is None and total is None:
        return None
    if total is None:
        total = (prompt or 0) + (completion or 0)
    return Usage(input_tokens=prompt, output_tokens=completion, total_tokens=total, raw=dict(raw))


def _public_usage(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    usage = decode_usage(raw)
    return usage.to_public_dict() if usage is not None else None


def _split_content(content: Any) -> tuple[str, str]:
    """content 可能是字符串、单个 chunk 或 chunk 列表；返回 (正文, 思考)。"""
    if isinstance(content, str):
        return content, ""
    chunks = content if isinstance(content, list) else [content]
    texts: list[str] = []
    thinking: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") == "text" and isinstance(chunk.get("text"), str):
            texts.append(chunk["text"])
        elif chunk.get("type") == "thinking" and isinstance(chunk.get("thinking"), list):
            for part in chunk["thinking"]:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    thinking.append(part["text"])
    return "".join(texts), "".join(thinking)


def _text_chunks(text: str) -> list[str]:
    size = max(1, STREAM_TEXT_CHUNK_SIZE)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _tool_call(tool_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {"id": tool_id, "type": "function", "function": {"name": name, "arguments": arguments or "{}"}}


async def _complete(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
    as_message: bool,
) -> ChatCompletionResult | ChatCompletionMessage:
    url = _api_root(base_url) + _CONVERSATIONS_PATH
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key, config.auth_style),
        **_extra_headers(config),
    }
    payload = _build_payload(messages=messages, config=config, stream=False)
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
            try:
                data = r.json()
            except (TypeError, json.JSONDecodeError) as exc:
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无法解析的 JSON",
                    detail=f"conversations: {exc}",
                ) from exc
            if not isinstance(data, dict) or not isinstance(data.get("outputs"), list):
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效响应",
                    detail="conversations: outputs is missing or not a list",
                )
            _log.set_response(body=data)
            texts: list[str] = []
            reasoning: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for entry in data["outputs"]:
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") == "message.output":
                    text, thinking = _split_content(entry.get("content"))
                    texts.append(text)
                    reasoning.append(thinking)
                elif entry.get("type") == "function.call":
                    tool_calls.append(
                        _tool_call(
                            str(entry.get("tool_call_id") or ""),
                            str(entry.get("name") or ""),
                            _arguments_text(entry.get("arguments")),
                        )
                    )
            text = "".join(texts)
            reasoning_text = "".join(reasoning).strip() or None
            if not text.strip() and not reasoning_text and not tool_calls:
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务未返回有效文本",
                    detail="conversations: empty outputs",
                )
            usage = _public_usage(data.get("usage") if isinstance(data.get("usage"), dict) else None)
            if as_message:
                return ChatCompletionMessage(
                    role="assistant",
                    content=text,
                    reasoning_content=reasoning_text,
                    tool_calls=tool_calls or None,
                    usage=usage,
                )
            return ChatCompletionResult(text=text, usage=usage)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=_SOURCE,
            default_code="provider_request_failed",
            default_message="Mistral 请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


def _stream_error_event(data: dict[str, Any]) -> AppError:
    code = data.get("code") if isinstance(data.get("code"), int) else None
    detail = f"{data.get('message') or 'conversation.response.error'}" + (f" (code {code})" if code else "")
    if code in {401, 403}:
        return _error(
            code="provider_auth_failed",
            message="上游服务鉴权失败",
            detail=detail,
            status_code=code,
            upstream_status=code,
            suggested_action="检查 API Key、账号权限和所选 API 预设",
        )
    if code == 429:
        return _error(
            code="provider_quota_exceeded",
            message="上游服务额度不足或请求过于频繁",
            detail=detail,
            status_code=429,
            retryable=True,
            upstream_status=code,
            suggested_action="检查账户额度，或稍后重试",
        )
    return _error(
        code="upstream_request_failed",
        message="Mistral 流式返回错误",
        detail=detail,
        retryable=True,
        upstream_status=code if isinstance(code, int) and code >= 100 else None,
        suggested_action="稍后重试，并检查模型名称和上游服务状态",
    )


async def _iter_events(response: httpx.Response, partial: Any) -> AsyncIterator[dict[str, Any]]:
    lines = response.aiter_lines()
    while True:
        try:
            line = await lines.__anext__()
        except StopAsyncIteration:
            return
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as exc:
            raise stream_interrupted_error(
                exc, partial=bool(partial()), source=f"{_SOURCE}.stream", provider=_PROVIDER, protocol=_PROTOCOL
            ) from exc
        if not line or not line.startswith("data:"):
            continue
        data_text = line[len("data:") :].strip()
        if not data_text or data_text == "[DONE]":
            continue
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError as exc:
            raise _error(code="stream_event_invalid", message="上游流包含无法解析的 JSON", detail=str(exc)) from exc
        if not isinstance(data, dict):
            raise _error(code="stream_event_invalid", message="上游流事件不是对象", detail=f"got {type(data).__name__}")
        yield data


async def _stream(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
) -> AsyncIterator[StreamChunk]:
    url = _api_root(base_url) + _CONVERSATIONS_PATH
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_auth_headers(api_key, config.auth_style),
        **_extra_headers(config),
    }
    payload = _build_payload(messages=messages, config=config, stream=True)

    aggregated_text: list[str] = []
    aggregated_reasoning: list[str] = []
    tools: dict[str, dict[str, str]] = {}
    usage_raw: dict[str, Any] | None = None
    saw_done = False
    try:
        async with log_outbound(
            source="llm",
            method="POST",
            url=url,
            request_headers=headers,
            request_body=payload,
            streaming=True,
        ) as _log:
            client = get_async_http_client()
            async with client.stream("POST", url, headers=headers, json=payload, timeout=None) as r:
                _log.set_response(status=r.status_code, headers=dict(r.headers))
                await _raise_stream_http_error(r)
                async for data in _iter_events(r, lambda: bool(aggregated_text or aggregated_reasoning or tools)):
                    event = data.get("type")
                    if event == "message.output.delta":
                        text, thinking = _split_content(data.get("content"))
                        if thinking:
                            aggregated_reasoning.append(thinking)
                            for piece in _text_chunks(thinking):
                                yield StreamChunk(kind="reasoning", text=piece)
                        if text:
                            aggregated_text.append(text)
                            for piece in _text_chunks(text):
                                yield StreamChunk(kind="content", text=piece)
                    elif event == "function.call.delta":
                        tool_id = str(data.get("tool_call_id") or data.get("id") or "")
                        slot = tools.setdefault(tool_id, {"name": "", "arguments": ""})
                        if isinstance(data.get("name"), str) and data["name"]:
                            slot["name"] = data["name"]
                        if isinstance(data.get("arguments"), str):
                            slot["arguments"] += data["arguments"]
                    elif event == "conversation.response.done":
                        saw_done = True
                        if isinstance(data.get("usage"), dict):
                            usage_raw = data["usage"]
                    elif event == "conversation.response.error":
                        raise _stream_error_event(data)

            tool_calls: list[dict[str, Any]] = []
            for tool_id, slot in tools.items():
                arguments = slot["arguments"].strip()
                if arguments:
                    try:
                        json.loads(arguments)
                    except json.JSONDecodeError as exc:
                        raise _error(code="stream_event_invalid", message="工具参数不是有效 JSON", detail=str(exc)) from exc
                tool_calls.append(_tool_call(tool_id, slot["name"], arguments))
            _log.set_response(
                body={
                    "_aggregated": True,
                    "content": "".join(aggregated_text),
                    "reasoning_content": "".join(aggregated_reasoning) or None,
                    "tool_calls": tool_calls or None,
                    "usage": usage_raw,
                }
            )
            if not saw_done:
                raise _error(
                    code="stream_incomplete",
                    message="Mistral 响应流提前中断",
                    detail="missing conversation.response.done",
                    retryable=True,
                )
            if not aggregated_text and not aggregated_reasoning and not tool_calls:
                raise _error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="conversations stream produced no content",
                )
            yield StreamChunk(kind="finish", tool_calls=tool_calls or None, usage=_public_usage(usage_raw))
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=f"{_SOURCE}.stream",
            default_code="provider_request_failed",
            default_message="Mistral 流式请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def _list_models(*, base_url: str, api_key: str, auth_style: str | None) -> list[str]:
    url = _api_root(base_url) + "/v1/models"
    headers = {"Accept": "application/json", **_auth_headers(api_key, auth_style)}
    try:
        async with log_outbound(source="llm", method="GET", url=url, request_headers=headers, streaming=False) as _log:
            client = get_async_http_client()
            r = await client.get(url, headers=headers, timeout=60)
            _log.set_response(status=r.status_code, headers=dict(r.headers), text=r.text)
            _raise_http_error(r)
            try:
                data = r.json()
            except (TypeError, json.JSONDecodeError) as exc:
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无法解析的 JSON",
                    detail=f"models: {exc}",
                ) from exc
            items = data.get("data") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效模型列表",
                    detail="models.data is missing or not a list",
                )
            out: set[str] = set()
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                capabilities = item.get("capabilities")
                if isinstance(capabilities, dict) and capabilities.get("completion_chat") is False:
                    continue
                out.add(item["id"].strip())
            return sorted(m for m in out if m)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=f"{_SOURCE}.models",
            default_code="provider_request_failed",
            default_message="获取 Mistral 模型列表失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


class MistralConversationsAdapter:
    provider = _PROVIDER
    protocol = _PROTOCOL

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        if not (base_url or "").strip():
            raise _error(
                code="config_missing",
                message="API 基础地址未配置",
                detail="base_url is empty",
                status_code=400,
                suggested_action="填写 https://api.mistral.ai",
            )
        if not (api_key or "").strip():
            raise _error(
                code="config_missing",
                message="API Key 未配置",
                detail="api_key is empty",
                status_code=400,
                suggested_action="在 API 预设中填写 Mistral API Key",
            )

    def build_request(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> WireRequest:
        self.validate_config(base_url=base_url, api_key=api_key)
        return WireRequest(
            method="POST",
            url=_api_root(base_url) + _CONVERSATIONS_PATH,
            headers={
                "Accept": "text/event-stream" if config.stream else "application/json",
                "Content-Type": "application/json",
                **_auth_headers(api_key, config.auth_style),
                **_extra_headers(config),
            },
            json_body=_build_payload(messages=messages, config=config, stream=bool(config.stream)),
        )

    async def list_models(
        self,
        *,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        auth_style: str | None = None,
    ) -> list[str]:
        self.validate_config(base_url=base_url, api_key=api_key)
        return await _list_models(base_url=base_url, api_key=api_key, auth_style=auth_style)

    async def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
        as_message: bool = False,
    ) -> Any:
        self.validate_config(base_url=base_url, api_key=api_key)
        return await _complete(base_url=base_url, api_key=api_key, messages=messages, config=config, as_message=as_message)

    async def stream(
        self,
        *,
        base_url: str,
        api_key: str,
        messages: list[dict[str, Any]],
        config: GenerationConfig,
    ) -> AsyncIterator[StreamChunk]:
        self.validate_config(base_url=base_url, api_key=api_key)
        async for chunk in _stream(base_url=base_url, api_key=api_key, messages=messages, config=config):
            yield chunk

    def decode_usage(self, raw: dict[str, Any] | None) -> Usage | None:
        return decode_usage(raw)
