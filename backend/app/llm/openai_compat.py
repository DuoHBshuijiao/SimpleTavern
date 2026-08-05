"""
OpenAI兼容API封装模块

本模块提供与OpenAI API兼容的HTTP客户端封装，支持：
- 模型列表查询
- 非流式聊天完成调用
- 流式聊天完成调用
- 工具调用支持

主要功能：
    - URL规范化：统一处理API基础URL格式
    - 认证处理：生成Bearer Token认证头
    - 请求构建：构建符合OpenAI格式的请求体
    - 响应解析：解析OpenAI格式的响应数据
    - 流式处理：处理Server-Sent Events (SSE) 流式响应

主要类：
    - ChatCompletionDelta: 流式响应增量数据
    - ChatCompletionResult: 非流式响应结果
    - ChatCompletionMessage: 完整的消息结构（包含工具调用等）

主要函数：
    - list_models_openai_compat: 获取可用模型列表
    - chat_completions: 非流式聊天完成
    - chat_completions_message: 非流式聊天完成（返回完整消息结构）
    - stream_chat_completions: 流式聊天完成

文件关系：
    - 被导入：被routes/llm.py、routes/generate.py、routes/assistant.py导入
    - 导入：仅导入标准库和第三方库（httpx、json等）
    - 依赖：无依赖其他应用模块
    - 位置：LLM API封装层，提供统一的OpenAI兼容接口
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlsplit, urlunsplit

from app.services.http_client import get_async_http_client

import httpx

from app.errors import AppError, as_app_error
from app.services.http_log import log_outbound

# 上游 4xx/5xx 响应体最大展示长度（避免日志/UI 被巨页吞没）
_MAX_ERROR_BODY_CHARS = 12000
_OPENAI_COMPAT_PROVIDER = "openai_compatible"
_OPENAI_COMPAT_PROTOCOL = "openai_compatible_chat"


def _protocol_error(
    *,
    code: str,
    message: str,
    detail: str,
    retryable: bool = False,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        detail=detail,
        source="llm.openai_compat",
        status_code=502,
        retryable=retryable,
        provider=_OPENAI_COMPAT_PROVIDER,
        protocol=_OPENAI_COMPAT_PROTOCOL,
        suggested_action="检查 API 预设与上游服务是否兼容 OpenAI Chat Completions 协议",
    )


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


def _first_choice(data: dict[str, Any], *, context: str) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _protocol_error(
            code="provider_response_invalid",
            message="上游服务未返回有效的生成结果",
            detail=f"{context}: choices is missing or empty",
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise _protocol_error(
            code="provider_response_invalid",
            message="上游服务返回了无效生成结果",
            detail=f"{context}: choices[0] is not an object",
        )
    return first


def _upstream_http_error_text(body: str) -> str:
    """
    从上游 JSON 中尽量提取可读错误（OpenAI error.message、Gemini error.message 等），
    否则回退为截断后的原始 body。httpx 默认的 HTTPStatusError 字符串不含响应体，调试时难以定位。
    """
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
            status = err.get("status")
            code = err.get("code")
            bits: list[str] = [m.strip()]
            if status:
                bits.append(str(status))
            elif code is not None:
                bits.append(str(code))
            return ": ".join(bits) if len(bits) > 1 else bits[0]
    if isinstance(err, str) and err.strip():
        return err.strip()
    m = data.get("message")
    if isinstance(m, str) and m.strip():
        return m.strip()
    return raw[:_MAX_ERROR_BODY_CHARS]


def _raise_http_error(r: httpx.Response) -> None:
    """非流式响应：失败时抛出带响应正文的 HTTPStatusError。"""
    if r.status_code < 400:
        return
    detail = _upstream_http_error_text(r.text or "")
    msg = f"HTTP {r.status_code} {r.reason_phrase} for {r.url}\n{detail}"
    raise httpx.HTTPStatusError(msg, request=r.request, response=r)


async def _raise_stream_http_error(r: httpx.Response) -> None:
    """流式响应：必须先读完全 body，否则 text 不可用。"""
    if r.status_code < 400:
        return
    await r.aread()
    detail = _upstream_http_error_text(r.text or "")
    msg = f"HTTP {r.status_code} {r.reason_phrase} for {r.url}\n{detail}"
    raise httpx.HTTPStatusError(msg, request=r.request, response=r)


def _normalize_base_url(base_url: str) -> str:
    """
    规范化API基础URL（用于拼接 /models、/chat/completions 等路径）。

    - 仅主机、无 path（或 path 仅为 /）时自动补 ``/v1``（兼容仅填域名或 ``api.openai.com``）。
    - 若已含任意非空 path（如 ``/v1beta/openai``、``/api/paas/v4``、``/compatible-mode/v1``），
      则保持原样，不再追加 ``/v1``，以免破坏 Google AI Studio、智谱等非标准路径。

    支持末尾有无 ``/``；无协议时补 ``https://``。
    """
    base = base_url.strip()
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


_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def _chat_completions_url(base_url: str) -> str:
    """
    返回用于请求的 chat completions 完整 URL。
    若用户填入的 base_url 已包含 /chat/completions，则直接使用（仅做末尾斜杠规范化），
    否则在规范化 base 后拼接 /chat/completions。
    """
    raw = base_url.strip()
    if not raw:
        raise ValueError(
            "API 基础地址未配置或为空。请在全局设置中填写「默认 API 基础地址」，"
            "或确保至少有一个 API 预设填写了 Base URL。"
        )
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    if _CHAT_COMPLETIONS_SUFFIX in raw.lower():
        return raw
    return _normalize_base_url(raw) + _CHAT_COMPLETIONS_SUFFIX


def _models_url(base_url: str) -> str:
    """
    返回用于请求的 models 列表完整 URL。
    若用户填入的 base_url 已包含 /chat/completions，则先去掉该部分得到 base，再拼接 /models。
    """
    raw = base_url.strip()
    if not raw:
        raise ValueError(
            "API 基础地址未配置或为空。请在全局设置中填写「默认 API 基础地址」，"
            "或确保至少有一个 API 预设填写了 Base URL。"
        )
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    lower = raw.lower()
    if _CHAT_COMPLETIONS_SUFFIX in lower:
        idx = lower.rfind(_CHAT_COMPLETIONS_SUFFIX)
        base_for_models = raw[:idx].rstrip("/")
        return _normalize_base_url(base_for_models) + "/models"
    return _normalize_base_url(raw) + "/models"


# OpenRouter 等平台用于展示来源的请求头（可选，便于在 openrouter.ai 等站点被识别）
_APP_REFERER = "https://github.com/DuoHBshuijiao/SimpleTavern"
_APP_TITLE = "SimpleTavern"


def _auth_headers(api_key: str) -> dict[str, str]:
    """
    生成认证请求头
    
    Args:
        api_key: API密钥
    
    Returns:
        dict[str, str]: 包含Authorization头的字典，如果api_key为空则返回空字典
    """
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _common_headers(api_key: str) -> dict[str, str]:
    """
    生成通用请求头（认证 + 应用标识）。
    应用标识头用于 OpenRouter 等平台展示来源与标题。
    """
    return {
        "HTTP-Referer": _APP_REFERER,
        "X-Title": _APP_TITLE,
        **_auth_headers(api_key),
    }


async def list_models_openai_compat(base_url: str, api_key: str) -> list[str]:
    """
    获取OpenAI兼容API的可用模型列表
    
    调用/v1/models端点获取模型列表，解析并返回模型ID列表。
    
    Args:
        base_url: API基础URL
        api_key: API密钥
    
    Returns:
        list[str]: 模型ID列表，按字母顺序排序并去重

    Raises:
        AppError: 配置、网络、鉴权或上游响应无效时抛出结构化错误
    """
    if not (base_url or "").strip():
        raise AppError(
            code="config_missing",
            message="API 基础地址未配置",
            source="llm.openai_compat.models",
            status_code=400,
            suggested_action="在 API 预设中填写 Base URL 后重试",
            provider="openai_compatible",
            protocol="openai_compatible_chat",
        )
    try:
        url = _models_url(base_url)
        headers = {"Accept": "application/json", **_common_headers(api_key)}
        async with log_outbound(
            source="llm",
            method="GET",
            url=url,
            request_headers=headers,
            streaming=False,
        ) as outbound_log:
            client = get_async_http_client()
            response = await client.get(url, headers=headers, timeout=10)
            outbound_log.set_response(
                status=response.status_code,
                headers=dict(response.headers),
                text=response.text,
            )
            _raise_http_error(response)
            data = response.json()
            outbound_log.set_response(body=data)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise AppError(
                code="provider_response_invalid",
                message="模型列表响应格式无效",
                detail="响应缺少 data 数组",
                source="llm.openai_compat.models",
                status_code=502,
                provider="openai_compatible",
                protocol="openai_compatible_chat",
                suggested_action="检查 API 预设是否使用 OpenAI-compatible 协议",
            )
        out: list[str] = []
        for item in data["data"]:
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
            source="llm.openai_compat.models",
            default_code="provider_request_failed",
            default_message="获取上游模型列表失败",
            default_status_code=502,
            provider="openai_compatible",
            protocol="openai_compatible_chat",
        ) from exc


@dataclass(frozen=True)
class ChatCompletionDelta:
    """
    聊天完成流式响应增量数据
    
    表示流式响应中的单个文本增量。
    
    主要属性：
        text: 增量文本内容
    """
    text: str


# 上游可能一次返回大块 reasoning/content，按此大小拆成小段逐段 yield，保证前端流式逐字/逐段显示
STREAM_TEXT_CHUNK_SIZE = 1


@dataclass(frozen=True)
class StreamChunk:
    """
    流式响应块（内容、思考链或结束标记）
    
    当 API 在 delta 中返回 content 或 reasoning_content 时，
    分别以 kind='content' 或 kind='reasoning' 逐块 yield，以保持打字机效果。
    大块文本会按 STREAM_TEXT_CHUNK_SIZE 拆成小段逐段 yield，避免整块输出。
    流结束时 yield kind='finish'，并携带可选的 tool_calls（用于 assistant 多轮工具调用）。
    """
    kind: Literal["content", "reasoning", "finish"]
    text: str = ""
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ChatCompletionResult:
    """
    聊天完成非流式响应结果
    
    表示非流式调用的完整响应文本。
    
    主要属性：
        text: 完整的响应文本
    """
    text: str


@dataclass(frozen=True)
class ChatCompletionMessage:
    """
    聊天完成消息结构
    
    包含完整的消息信息，支持工具调用等扩展功能。
    
    主要属性：
        role: 消息角色（system/user/assistant）
        content: 消息文本内容
        reasoning_content: 推理内容（某些模型支持）
        tool_calls: 工具调用列表
    """
    role: str | None
    content: str | None
    reasoning_content: str | None
    tool_calls: list[dict[str, Any]] | None


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    stream: bool,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    tools: list[dict[str, Any]] | None,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    构建OpenAI兼容的请求体
    
    Args:
        model: 模型名称
        messages: 消息列表
        stream: 是否启用流式输出
        temperature: 温度参数
        top_p: 核采样参数
        max_tokens: 最大生成token数
        tools: 工具定义列表
        extra_body: 额外的请求体字段
    
    Returns:
        dict[str, Any]: 构建好的请求体字典
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
        payload.setdefault("max_completion_tokens", max_tokens)
    if tools:
        payload["tools"] = tools
    if extra_body:
        payload.update(extra_body)
    return payload


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
) -> ChatCompletionResult:
    """
    OpenAI兼容的非流式聊天完成调用
    
    调用/v1/chat/completions端点，等待完整响应后返回。
    
    Args:
        base_url: API基础URL
        api_key: API密钥
        model: 模型名称
        messages: 消息列表
        temperature: 温度参数，控制输出随机性
        top_p: 核采样参数，控制输出多样性
        max_tokens: 最大生成token数
        tools: 工具定义列表
        extra_body: 额外的请求体字段
    
    Returns:
        ChatCompletionResult: 包含完整响应文本的结果对象
    
    Raises:
        httpx.HTTPStatusError: HTTP请求失败时抛出
    """
    url = _chat_completions_url(base_url)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_common_headers(api_key),
    }

    payload = _build_payload(
        model=model,
        messages=messages,
        stream=False,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=extra_body,
    )

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
        data = _decode_json_object(r, context="chat completion response")
        _log.set_response(body=data)
        choice = _first_choice(data, context="chat completion response")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务未返回有效消息",
                detail="chat completion response: choices[0].message is missing or invalid",
            )
        content = _message_content_to_text(message.get("content"))
        if not content.strip():
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务返回了空消息",
                detail="chat completion response: assistant content is empty",
            )
        return ChatCompletionResult(text=content)


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
) -> ChatCompletionMessage:
    """
    OpenAI兼容的非流式聊天完成调用（返回完整消息结构）
    
    调用/v1/chat/completions端点，返回包含角色、内容、推理内容和工具调用的完整消息结构。
    
    Args:
        base_url: API基础URL
        api_key: API密钥
        model: 模型名称
        messages: 消息列表
        temperature: 温度参数
        top_p: 核采样参数
        max_tokens: 最大生成token数
        tools: 工具定义列表
        extra_body: 额外的请求体字段
    
    Returns:
        ChatCompletionMessage: 完整的消息结构对象
    
    Raises:
        httpx.HTTPStatusError: HTTP请求失败时抛出
    """
    url = _chat_completions_url(base_url)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_common_headers(api_key),
    }
    payload = _build_payload(
        model=model,
        messages=messages,
        stream=False,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=extra_body,
    )
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
        data = _decode_json_object(r, context="chat completion message response")
        _log.set_response(body=data)
        choice = _first_choice(data, context="chat completion message response")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务未返回有效消息",
                detail="chat completion message response: choices[0].message is missing or invalid",
            )
        # 支持 reasoning_content（OpenAI）与 reasoning（如 Gemini/OpenRouter）两种字段名
        reasoning_content = message.get("reasoning_content") or message.get("reasoning")
        if reasoning_content is not None and not isinstance(reasoning_content, str):
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务返回了无效 reasoning",
                detail="chat completion message response: reasoning must be a string",
            )
        content = _message_content_to_text(message.get("content")) or None
        tool_calls = message.get("tool_calls")
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务返回了无效工具调用",
                detail="chat completion message response: tool_calls is not an array",
            )
        if content is None and not reasoning_content and not tool_calls:
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游服务返回了空消息",
                detail="chat completion message response: content, reasoning and tool_calls are empty",
            )
        return ChatCompletionMessage(
            role=message.get("role"),
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )


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
) -> AsyncIterator[StreamChunk]:
    """
    OpenAI兼容的流式聊天完成调用
    
    解析 SSE 流中的 delta.content 与 delta.reasoning_content（若有），
    分别以 StreamChunk(kind='content'|'reasoning', text=...) 逐块 yield，保持打字机效果。
    
    Yields:
        StreamChunk: 流式响应块（content 或 reasoning）
    """
    url = _chat_completions_url(base_url)
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_common_headers(api_key),
    }

    payload = _build_payload(
        model=model,
        messages=messages,
        stream=True,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
        extra_body=extra_body,
    )

    # 流式响应中 tool_calls 按 index 分片到达，按 index 合并为完整列表
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    saw_done = False
    saw_finish_reason = False
    saw_output = False

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
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith(":"):
                    # SSE comment / keepalive 帧无业务语义，可安全跳过。
                    continue
                if not line.startswith("data:"):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流包含未知事件帧",
                        detail=f"unexpected SSE line: {line[:200]}",
                    )
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    saw_done = True
                    break
                if not data_str:
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流包含空数据帧",
                        detail="SSE data field is empty",
                    )
                try:
                    obj = json.loads(data_str)
                except json.JSONDecodeError as exc:
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流包含无法解析的 JSON",
                        detail=f"invalid SSE JSON: {exc}",
                    ) from exc
                if not isinstance(obj, dict):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流事件格式无效",
                        detail=f"expected object, got {type(obj).__name__}",
                    )

                choices = obj.get("choices")
                if not choices:
                    # OpenAI-compatible 服务可在独立帧中只返回 usage。
                    if obj.get("usage") is not None:
                        continue
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流事件缺少 choices",
                        detail="SSE event contains neither choices nor usage",
                    )
                if not isinstance(choices, list) or not isinstance(choices[0], dict):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流事件 choices 格式无效",
                        detail="choices must be a non-empty array of objects",
                    )
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                if isinstance(finish_reason, str) and finish_reason:
                    saw_finish_reason = True
                delta = choice.get("delta")
                if delta is None:
                    delta = {}
                if not isinstance(delta, dict):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流事件 delta 格式无效",
                        detail="choices[0].delta must be an object",
                    )
                # 支持 reasoning_content（OpenAI）与 reasoning（如 Gemini/OpenRouter）两种字段名
                reasoning_text = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning_text is not None and not isinstance(reasoning_text, str):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流 reasoning 格式无效",
                        detail="reasoning delta must be a string",
                    )
                if isinstance(reasoning_text, str) and reasoning_text:
                    saw_output = True
                    aggregated_reasoning.append(reasoning_text)
                    for i in range(0, len(reasoning_text), STREAM_TEXT_CHUNK_SIZE):
                        yield StreamChunk(kind="reasoning", text=reasoning_text[i : i + STREAM_TEXT_CHUNK_SIZE])
                content_text = delta.get("content")
                if content_text is not None and not isinstance(content_text, str):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流正文格式无效",
                        detail="content delta must be a string",
                    )
                if isinstance(content_text, str) and content_text:
                    saw_output = True
                    aggregated_content.append(content_text)
                    _log.append_stream_text(content_text)
                    for i in range(0, len(content_text), STREAM_TEXT_CHUNK_SIZE):
                        yield StreamChunk(kind="content", text=content_text[i : i + STREAM_TEXT_CHUNK_SIZE])
                # 收集流式 tool_calls（OpenAI 格式：delta.tool_calls 为按 index 的增量）
                raw_tool_calls = delta.get("tool_calls")
                if raw_tool_calls is None:
                    continue
                if not isinstance(raw_tool_calls, list):
                    raise _protocol_error(
                        code="stream_event_invalid",
                        message="上游流工具调用格式无效",
                        detail="tool_calls delta must be an array",
                    )
                for tc in raw_tool_calls:
                    if not isinstance(tc, dict):
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流工具调用格式无效",
                            detail="tool call delta must be an object",
                        )
                    idx = tc.get("index")
                    if not isinstance(idx, int) or idx < 0:
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流工具调用缺少有效索引",
                            detail="tool call delta index must be a non-negative integer",
                        )
                    saw_output = True
                    if idx not in tool_calls_by_index:
                        tool_calls_by_index[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    cur = tool_calls_by_index[idx]
                    if tc.get("id") is not None:
                        if not isinstance(tc["id"], str):
                            raise _protocol_error(
                                code="stream_event_invalid",
                                message="上游流工具调用 ID 格式无效",
                                detail="tool call id delta must be a string",
                            )
                        cur["id"] = (cur.get("id") or "") + tc["id"]
                    fn = tc.get("function")
                    if fn is not None and not isinstance(fn, dict):
                        raise _protocol_error(
                            code="stream_event_invalid",
                            message="上游流工具函数格式无效",
                            detail="tool call function delta must be an object",
                        )
                    if isinstance(fn, dict):
                        if fn.get("name") is not None:
                            if not isinstance(fn["name"], str):
                                raise _protocol_error(
                                    code="stream_event_invalid",
                                    message="上游流工具函数名称格式无效",
                                    detail="tool function name delta must be a string",
                                )
                            cur["function"]["name"] = (cur["function"].get("name") or "") + fn["name"]
                        if fn.get("arguments") is not None:
                            if not isinstance(fn["arguments"], str):
                                raise _protocol_error(
                                    code="stream_event_invalid",
                                    message="上游流工具参数格式无效",
                                    detail="tool function arguments delta must be a string",
                                )
                            cur["function"]["arguments"] = (cur["function"].get("arguments") or "") + fn["arguments"]
        if not saw_output:
            raise _protocol_error(
                code="provider_response_invalid",
                message="上游流未返回任何有效内容",
                detail="stream ended without content, reasoning, or tool calls",
            )
        if not saw_done and not saw_finish_reason:
            raise _protocol_error(
                code="stream_interrupted",
                message="上游流在完成前中断",
                detail="stream ended without [DONE] or finish_reason",
                retryable=True,
            )
        # 流结束：产出 finish，便于调用方判断是否有 tool_calls 并继续多轮
        sorted_tool_calls = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())] if tool_calls_by_index else None
        # 把聚合的流式正文写入日志，便于后续查看
        aggregated_body: dict[str, Any] = {
            "_aggregated": True,
            "content": "".join(aggregated_content),
        }
        if aggregated_reasoning:
            aggregated_body["reasoning_content"] = "".join(aggregated_reasoning)
        if sorted_tool_calls:
            aggregated_body["tool_calls"] = sorted_tool_calls
        _log.set_response(body=aggregated_body)
        yield StreamChunk(kind="finish", tool_calls=sorted_tool_calls)
