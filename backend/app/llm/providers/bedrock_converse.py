"""AWS Bedrock Converse / ConverseStream 适配器（T-832）。

依据：
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html （Bearer 鉴权）
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html （cachePoint）

只支持 Bearer（Bedrock API Key），不实现 SigV4。
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, AsyncIterator
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.errors import AppError, as_app_error
from app.llm.aws_eventstream import (
    EVENTSTREAM_CONTENT_TYPE,
    aiter_event_frames,
    frame_json,
)
from app.llm.prompt_cache import MODE_EXPLICIT, PromptCachePlan
from app.llm.providers.openai_compatible_chat import (
    STREAM_TEXT_CHUNK_SIZE,
    ChatCompletionMessage,
    ChatCompletionResult,
    StreamChunk,
    _raise_http_error,
    _raise_stream_http_error,
)
from app.llm.types import (
    BEDROCK_CONVERSE_PROTOCOL,
    GenerationConfig,
    Usage,
    WireRequest,
    auth_headers_for_style,
)
from app.llm.vertex_auth import looks_like_service_account_json
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound

_PROVIDER = "amazon-bedrock"
_PROTOCOL = BEDROCK_CONVERSE_PROTOCOL
_SOURCE = "llm.bedrock_converse"
_DEFAULT_THINKING_ANSWER_TOKENS = 4096
_MIN_THINKING_BUDGET = 1024
# 这些停止原因说明输出不可用，不能当成正常结束
_FAILED_STOP_REASONS = {"malformed_model_output", "malformed_tool_use"}

# 带签名的 reasoning 块必须原样回传（工具轮次），但业务层只传 reasoning_content 文本。
# 这里按 toolUseId 在进程内保留最近的块；进程重启后丢失，对旧模型的工具续轮会由上游报错。
_REASONING_MEMORY_LIMIT = 512
_reasoning_by_tool_id: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()


def _remember_reasoning(blocks: list[dict[str, Any]], tool_ids: list[str]) -> None:
    if not blocks or not tool_ids:
        return
    _reasoning_by_tool_id[tool_ids[0]] = blocks
    _reasoning_by_tool_id.move_to_end(tool_ids[0])
    while len(_reasoning_by_tool_id) > _REASONING_MEMORY_LIMIT:
        _reasoning_by_tool_id.popitem(last=False)


def _error(
    *,
    code: str,
    message: str,
    detail: str,
    retryable: bool = False,
    status_code: int = 502,
    suggested_action: str = "检查 Bedrock 预设（Base URL / API Key / 模型）与协议是否匹配",
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
    )


def _unsupported(message: str, detail: str, *, suggested_action: str = "换用支持该能力的模型或协议") -> AppError:
    return _error(
        code="provider_capability_unsupported",
        message=message,
        detail=detail,
        status_code=400,
        suggested_action=suggested_action,
    )


def _normalize_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw:
        raise _error(code="config_missing", message="API 基础地址未配置", detail="base_url is empty", status_code=400)
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw.rstrip("/")


def _model_url(base_url: str, model: str, *, stream: bool) -> str:
    # ARN 里的 / 必须转义；模型 id 里的 : 按官方示例保留
    encoded = quote((model or "").strip(), safe=".-:_")
    action = "converse-stream" if stream else "converse"
    return f"{_normalize_base_url(base_url)}/model/{encoded}/{action}"


def _foundation_models_url(base_url: str) -> str:
    """模型列表在控制面（bedrock.<region>），推理在 bedrock-runtime.<region>；其余主机保持原样。"""
    parts = urlsplit(_normalize_base_url(base_url))
    netloc = parts.netloc
    if netloc.lower().startswith("bedrock-runtime."):
        netloc = "bedrock." + netloc[len("bedrock-runtime.") :]
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/") + "/foundation-models", "", ""))


def _auth_headers(api_key: str, auth_style: str | None) -> dict[str, str]:
    if looks_like_service_account_json(api_key):
        raise _error(
            code="config_invalid",
            message="Bedrock 预设的密钥不能是服务账号 JSON",
            detail="api key looks like a Google service account",
            status_code=400,
            suggested_action="填写 Bedrock API Key",
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
                        "当前 Bedrock Converse 适配器尚未支持图片输入",
                        f"content part type={item.get('type')}",
                        suggested_action="去掉图片后重试，或换用支持图片的协议",
                    )
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _parse_tool_arguments(raw: Any, *, name: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _error(
                code="tool_call_invalid",
                message="工具调用参数不是有效 JSON",
                detail=f"tool={name}: {exc}",
                status_code=400,
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    raise _error(
        code="tool_call_invalid",
        message="工具调用参数不是 JSON 对象",
        detail=f"tool={name}",
        status_code=400,
    )


def _assistant_blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    tool_uses: list[dict[str, Any]] = []
    tool_calls = msg.get("tool_calls")
    for tc in tool_calls if isinstance(tool_calls, list) else []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        tool_id = str(tc.get("id") or "")
        tool_uses.append(
            {"toolUse": {"toolUseId": tool_id, "name": name, "input": _parse_tool_arguments(fn.get("arguments"), name=name)}}
        )
    if tool_uses:
        first_id = tool_uses[0]["toolUse"]["toolUseId"]
        blocks.extend(_reasoning_by_tool_id.get(first_id, []))
    text = _content_to_text(msg.get("content"))
    if text.strip():
        blocks.append({"text": text})
    blocks.extend(tool_uses)
    return blocks


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """OpenAI 形状消息 → (system 块, Converse messages)。同角色相邻消息合并，首条必须是 user。"""
    system: list[dict[str, Any]] = []
    converted: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"].extend(blocks)
        else:
            converted.append({"role": role, "content": list(blocks)})

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip()
        if role == "system":
            text = _content_to_text(msg.get("content")).strip()
            if text:
                system.append({"text": text})
        elif role == "tool":
            text = _content_to_text(msg.get("content"))
            push(
                "user",
                [
                    {
                        "toolResult": {
                            "toolUseId": str(msg.get("tool_call_id") or ""),
                            "content": [{"text": text if text.strip() else "(empty)"}],
                        }
                    }
                ],
            )
        elif role == "assistant":
            push("assistant", _assistant_blocks(msg))
        elif role == "user":
            text = _content_to_text(msg.get("content"))
            if text.strip():
                push("user", [{"text": text}])
        else:
            raise _error(
                code="provider_request_invalid",
                message="消息角色不被 Bedrock Converse 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
    if not converted:
        raise _error(
            code="provider_request_invalid",
            message="没有可发送给 Bedrock 的对话消息",
            detail="messages empty after system extraction",
            status_code=400,
        )
    if converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": [{"text": "."}]})
    return system, converted


def _tool_spec(name: str, description: Any, schema: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "name": name,
        "inputSchema": {"json": schema if isinstance(schema, dict) else {"type": "object", "properties": {}}},
    }
    if isinstance(description, str) and description:
        spec["description"] = description
    return {"toolSpec": spec}


def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if fn is not None and tool.get("type") in {None, "function"}:
            name = str(fn.get("name") or "").strip()
            if name:
                out.append(_tool_spec(name, fn.get("description"), fn.get("parameters")))
            continue
        if isinstance(tool.get("name"), str) and isinstance(tool.get("input_schema"), dict):
            out.append(_tool_spec(tool["name"].strip(), tool.get("description"), tool["input_schema"]))
            continue
        raise _unsupported(
            "Bedrock Converse 不支持这种工具类型",
            f"tool type={tool.get('type')!r}",
            suggested_action="改用函数工具，或在预设中把联网来源设为独立搜索",
        )
    return out


def _convert_tool_choice(tool_choice: Any) -> dict[str, Any] | None:
    if tool_choice is None:
        return None
    choice = tool_choice
    if isinstance(choice, dict):
        typ = choice.get("type")
        fn = choice.get("function") if isinstance(choice.get("function"), dict) else {}
        name = fn.get("name") or choice.get("name")
        if typ in {"function", "tool"} and isinstance(name, str) and name.strip():
            return {"tool": {"name": name.strip()}}
        choice = typ
    key = str(choice or "").strip().lower()
    if key == "auto":
        return {"auto": {}}
    if key in {"any", "required"}:
        return {"any": {}}
    raise _unsupported("Bedrock Converse 不支持这种工具选择方式", f"tool_choice={key!r}")


def _history_tool_specs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """历史里有工具块但这次没带工具定义时，Converse 仍要求 toolConfig：按历史里的工具名补最小定义。"""
    names: dict[str, None] = {}
    for msg in messages:
        for block in msg["content"]:
            tool_use = block.get("toolUse")
            if isinstance(tool_use, dict):
                names[tool_use["name"]] = None
    has_results = any("toolResult" in block for msg in messages for block in msg["content"])
    if not names and not has_results:
        return []
    return [_tool_spec(name, None, None) for name in names]


def _cache_point(plan: PromptCachePlan) -> dict[str, Any]:
    point: dict[str, Any] = {"type": "default"}
    if plan.ttl == "1h":
        point["ttl"] = "1h"
    return {"cachePoint": point}


def _build_payload(*, messages: list[dict[str, Any]], config: GenerationConfig) -> dict[str, Any]:
    system, converted = _convert_messages(messages)
    extra = dict(config.extra_body or {})
    additional = extra.pop("additionalModelRequestFields", None)
    raw_tools = extra.pop("tools", None)
    raw_choice = extra.pop("tool_choice", None)
    stop = extra.pop("stop", None)
    extra.pop("anthropic_prompt_cache", None)
    leftovers = [k for k, v in extra.items() if v is not None]
    if leftovers:
        raise _unsupported("Bedrock Converse 不支持这些请求参数", "unsupported fields: " + ", ".join(sorted(leftovers)))

    plan = PromptCachePlan.from_dict(config.prompt_cache) if config.prompt_cache else None
    explicit_cache = plan is not None and plan.mode == MODE_EXPLICIT

    payload: dict[str, Any] = {"messages": converted}
    if system:
        payload["system"] = system
        if explicit_cache and "system" in plan.breakpoints:
            system.append(_cache_point(plan))
    if explicit_cache and "history_tail" in plan.breakpoints:
        converted[-1]["content"].append(_cache_point(plan))

    inference: dict[str, Any] = {}
    max_tokens = int(config.max_tokens) if config.max_tokens and config.max_tokens > 0 else None
    thinking = additional.get("thinking") if isinstance(additional, dict) else None
    thinking_type = thinking.get("type") if isinstance(thinking, dict) else None
    if thinking_type == "enabled":
        # 官方要求 budget_tokens < maxTokens，且不低于 1024
        budget = int(thinking.get("budget_tokens") or _MIN_THINKING_BUDGET)
        if max_tokens is None:
            max_tokens = budget + _DEFAULT_THINKING_ANSWER_TOKENS
        elif max_tokens <= budget:
            if max_tokens <= _MIN_THINKING_BUDGET:
                raise _unsupported(
                    "最大输出太小，无法开启思考",
                    f"maxTokens={max_tokens}; minimum thinking budget={_MIN_THINKING_BUDGET}",
                    suggested_action="调大最大输出，或关闭思考",
                )
            additional = {**additional, "thinking": {**thinking, "budget_tokens": max_tokens - 1}}
    if max_tokens is not None:
        inference["maxTokens"] = max_tokens
    if config.temperature is not None:
        inference["temperature"] = config.temperature
    if config.top_p is not None:
        inference["topP"] = config.top_p
    if stop:
        inference["stopSequences"] = [stop] if isinstance(stop, str) else list(stop)
    if inference:
        payload["inferenceConfig"] = inference
    if additional:
        payload["additionalModelRequestFields"] = additional

    specs = _convert_tools(config.tools if config.tools is not None else raw_tools)
    choice = _convert_tool_choice(config.tool_choice if config.tool_choice is not None else raw_choice)
    if not specs:
        specs = _history_tool_specs(converted)
    if specs:
        tool_config: dict[str, Any] = {"tools": specs}
        if explicit_cache and "tools" in plan.breakpoints:
            tool_config["tools"] = [*specs, _cache_point(plan)]
        if choice is not None:
            if thinking_type in {"enabled", "adaptive"} and ("any" in choice or "tool" in choice):
                raise _unsupported(
                    "开启思考时不能强制模型调用工具",
                    "thinking with forced tool use is rejected by Claude",
                    suggested_action="关闭思考，或把工具选择改为自动",
                )
            tool_config["toolChoice"] = choice
        payload["toolConfig"] = tool_config
    elif choice is not None:
        raise _unsupported("指定了工具选择但没有工具定义", "toolChoice without tools")
    return payload


def decode_usage(raw: dict[str, Any] | None) -> Usage | None:
    if not isinstance(raw, dict) or not raw:
        return None

    def as_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    input_tokens = as_int(raw.get("inputTokens"))
    output_tokens = as_int(raw.get("outputTokens"))
    total = as_int(raw.get("totalTokens"))
    if input_tokens is None and output_tokens is None and total is None:
        return None
    if total is None:
        total = (input_tokens or 0) + (output_tokens or 0)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cache_read_input_tokens=as_int(raw.get("cacheReadInputTokens")),
        cache_write_input_tokens=as_int(raw.get("cacheWriteInputTokens")),
        raw=dict(raw),
    )


def _public_usage(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    usage = decode_usage(raw)
    return usage.to_public_dict() if usage is not None else None


def _tool_call(tool_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {"id": tool_id, "type": "function", "function": {"name": name, "arguments": arguments or "{}"}}


def _check_stop_reason(stop_reason: Any) -> None:
    if stop_reason in _FAILED_STOP_REASONS:
        raise _error(
            code="tool_call_invalid" if stop_reason == "malformed_tool_use" else "provider_response_invalid",
            message="模型返回了格式错误的输出",
            detail=f"stopReason={stop_reason}",
            retryable=True,
        )


def _parse_output(data: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]] | None, list[dict[str, Any]]]:
    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    message = output.get("message") if isinstance(output.get("message"), dict) else None
    if message is None or not isinstance(message.get("content"), list):
        raise _error(
            code="provider_response_invalid",
            message="上游服务返回了无效响应",
            detail="converse: output.message.content is missing",
        )
    texts: list[str] = []
    reasoning_texts: list[str] = []
    reasoning_blocks: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    for block in message["content"]:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif isinstance(block.get("reasoningContent"), dict):
            reasoning_blocks.append(block)
            reasoning_text = block["reasoningContent"].get("reasoningText")
            if isinstance(reasoning_text, dict) and isinstance(reasoning_text.get("text"), str):
                reasoning_texts.append(reasoning_text["text"])
        elif isinstance(block.get("toolUse"), dict):
            tool_use = block["toolUse"]
            tool_calls.append(
                _tool_call(
                    str(tool_use.get("toolUseId") or ""),
                    str(tool_use.get("name") or ""),
                    json.dumps(tool_use.get("input") if tool_use.get("input") is not None else {}, ensure_ascii=False),
                )
            )
    _remember_reasoning(reasoning_blocks, [t["id"] for t in tool_calls])
    return "".join(texts), "".join(reasoning_texts).strip() or None, tool_calls or None, message["content"]


async def _complete(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
    as_message: bool,
) -> ChatCompletionResult | ChatCompletionMessage:
    url = _model_url(base_url, config.model, stream=False)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key, config.auth_style),
        **_extra_headers(config),
    }
    payload = _build_payload(messages=messages, config=config)
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
                    detail=f"converse: {exc}",
                ) from exc
            if not isinstance(data, dict):
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效响应",
                    detail=f"converse: expected object, got {type(data).__name__}",
                )
            _log.set_response(body=data)
            stop_reason = data.get("stopReason")
            _check_stop_reason(stop_reason)
            text, reasoning, tool_calls, content = _parse_output(data)
            if not text.strip() and not reasoning and not tool_calls:
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务未返回有效文本",
                    detail=f"converse: empty output; stopReason={stop_reason}",
                )
            usage = _public_usage(data.get("usage") if isinstance(data.get("usage"), dict) else None)
            if as_message:
                return ChatCompletionMessage(
                    role="assistant",
                    content=text,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls,
                    usage=usage,
                    provider_content=content,
                    stop_reason=stop_reason if isinstance(stop_reason, str) else None,
                )
            return ChatCompletionResult(text=text, usage=usage)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=_SOURCE,
            default_code="provider_request_failed",
            default_message="Bedrock 请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


def _text_chunks(text: str) -> list[str]:
    size = max(1, STREAM_TEXT_CHUNK_SIZE)
    return [text[i : i + size] for i in range(0, len(text), size)]


async def _stream(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
) -> AsyncIterator[StreamChunk]:
    url = _model_url(base_url, config.model, stream=True)
    headers = {
        "Accept": EVENTSTREAM_CONTENT_TYPE,
        "Content-Type": "application/json",
        **_auth_headers(api_key, config.auth_style),
        **_extra_headers(config),
    }
    payload = _build_payload(messages=messages, config=config)
    common = {"source": _SOURCE, "provider": _PROVIDER, "protocol": _PROTOCOL}

    aggregated_text: list[str] = []
    aggregated_reasoning: list[str] = []
    tools: dict[int, dict[str, str]] = {}
    reasoning_blocks: dict[int, dict[str, str]] = {}
    usage_raw: dict[str, Any] | None = None
    stop_reason: str | None = None
    saw_stop = False

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
                async for frame in aiter_event_frames(
                    r, partial=lambda: bool(aggregated_text or aggregated_reasoning or tools), **common
                ):
                    event = frame.event_type
                    if event not in {"contentBlockStart", "contentBlockDelta", "contentBlockStop", "messageStop", "metadata"}:
                        continue
                    data = frame_json(frame, **common)
                    if event == "contentBlockStart":
                        start = data.get("start") if isinstance(data.get("start"), dict) else {}
                        tool_use = start.get("toolUse")
                        index = data.get("contentBlockIndex")
                        if isinstance(tool_use, dict) and isinstance(index, int):
                            tools[index] = {
                                "id": str(tool_use.get("toolUseId") or ""),
                                "name": str(tool_use.get("name") or ""),
                                "input": "",
                            }
                    elif event == "contentBlockDelta":
                        delta = data.get("delta") if isinstance(data.get("delta"), dict) else {}
                        index = data.get("contentBlockIndex")
                        if isinstance(delta.get("text"), str) and delta["text"]:
                            aggregated_text.append(delta["text"])
                            for piece in _text_chunks(delta["text"]):
                                yield StreamChunk(kind="content", text=piece)
                        elif isinstance(delta.get("toolUse"), dict):
                            piece = delta["toolUse"].get("input")
                            if isinstance(index, int) and index in tools and isinstance(piece, str):
                                tools[index]["input"] += piece
                        elif isinstance(delta.get("reasoningContent"), dict) and isinstance(index, int):
                            reasoning = delta["reasoningContent"]
                            block = reasoning_blocks.setdefault(index, {})
                            for key in ("text", "signature", "redactedContent"):
                                if isinstance(reasoning.get(key), str):
                                    block[key] = block.get(key, "") + reasoning[key]
                            text = reasoning.get("text")
                            if isinstance(text, str) and text:
                                aggregated_reasoning.append(text)
                                for piece in _text_chunks(text):
                                    yield StreamChunk(kind="reasoning", text=piece)
                    elif event == "contentBlockStop":
                        index = data.get("contentBlockIndex")
                        if isinstance(index, int) and index in tools and tools[index]["input"].strip():
                            try:
                                json.loads(tools[index]["input"])
                            except json.JSONDecodeError as exc:
                                raise _error(
                                    code="stream_event_invalid",
                                    message="工具参数不是有效 JSON",
                                    detail=str(exc),
                                ) from exc
                    elif event == "messageStop":
                        saw_stop = True
                        if isinstance(data.get("stopReason"), str):
                            stop_reason = data["stopReason"]
                    elif event == "metadata" and isinstance(data.get("usage"), dict):
                        usage_raw = data["usage"]

            tool_calls = [
                _tool_call(tools[i]["id"], tools[i]["name"], tools[i]["input"].strip()) for i in sorted(tools)
            ] or None
            _log.set_response(
                body={
                    "_aggregated": True,
                    "content": "".join(aggregated_text),
                    "reasoning_content": "".join(aggregated_reasoning) or None,
                    "tool_calls": tool_calls,
                    "usage": usage_raw,
                    "stopReason": stop_reason,
                }
            )
            if not saw_stop:
                raise _error(
                    code="stream_incomplete",
                    message="Bedrock 响应流提前中断",
                    detail="missing messageStop",
                    retryable=True,
                )
            _check_stop_reason(stop_reason)
            if not aggregated_text and not aggregated_reasoning and not tool_calls:
                raise _error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail=f"converse-stream: empty output; stopReason={stop_reason}",
                )
            stored_reasoning: list[dict[str, Any]] = []
            for index in sorted(reasoning_blocks):
                block = reasoning_blocks[index]
                if block.get("redactedContent"):
                    stored_reasoning.append({"reasoningContent": {"redactedContent": block["redactedContent"]}})
                else:
                    reasoning_text: dict[str, Any] = {"text": block.get("text", "")}
                    if block.get("signature"):
                        reasoning_text["signature"] = block["signature"]
                    stored_reasoning.append({"reasoningContent": {"reasoningText": reasoning_text}})
            _remember_reasoning(stored_reasoning, [t["id"] for t in tool_calls or []])
            yield StreamChunk(
                kind="finish",
                tool_calls=tool_calls,
                usage=_public_usage(usage_raw),
                stop_reason=stop_reason,
            )
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=f"{_SOURCE}.stream",
            default_code="provider_request_failed",
            default_message="Bedrock 流式请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def _list_models(*, base_url: str, api_key: str, auth_style: str | None) -> list[str]:
    url = _foundation_models_url(base_url)
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
                    detail=f"foundation-models: {exc}",
                ) from exc
            summaries = data.get("modelSummaries") if isinstance(data, dict) else None
            if not isinstance(summaries, list):
                raise _error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效模型列表",
                    detail="modelSummaries is missing or not a list",
                )
            out: set[str] = set()
            for item in summaries:
                if not isinstance(item, dict) or not isinstance(item.get("modelId"), str):
                    continue
                modalities = item.get("outputModalities")
                if isinstance(modalities, list) and "TEXT" not in modalities:
                    continue
                out.add(item["modelId"].strip())
            return sorted(m for m in out if m)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source=f"{_SOURCE}.models",
            default_code="provider_request_failed",
            default_message="获取 Bedrock 模型列表失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


class BedrockConverseAdapter:
    provider = _PROVIDER
    protocol = _PROTOCOL

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        if not (base_url or "").strip():
            raise _error(
                code="config_missing",
                message="API 基础地址未配置",
                detail="base_url is empty",
                status_code=400,
                suggested_action="填写形如 https://bedrock-runtime.us-east-1.amazonaws.com 的地址",
            )
        if not (api_key or "").strip():
            raise _error(
                code="config_missing",
                message="API Key 未配置",
                detail="api_key is empty",
                status_code=400,
                suggested_action="在 API 预设中填写 Bedrock API Key",
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
            url=_model_url(base_url, config.model, stream=bool(config.stream)),
            headers={
                "Accept": EVENTSTREAM_CONTENT_TYPE if config.stream else "application/json",
                "Content-Type": "application/json",
                **_auth_headers(api_key, config.auth_style),
                **_extra_headers(config),
            },
            json_body=_build_payload(messages=messages, config=config),
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
