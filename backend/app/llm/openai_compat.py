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
from typing import Any, AsyncIterator

import httpx


def _normalize_base_url(base_url: str) -> str:
    """
    规范化API基础URL
    
    处理用户输入的各种URL格式，统一为包含/v1的完整URL。
    支持以下格式：
    - 完整URL（带/v1或不带）
    - 仅域名（自动添加https://和/v1）
    
    Args:
        base_url: 原始基础URL
    
    Returns:
        str: 规范化后的URL，确保以/v1结尾
    """
    base = base_url.strip()
    if base and not (base.startswith("http://") or base.startswith("https://")):
        base = "https://" + base
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return base
    return base + "/v1"


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


async def list_models_openai_compat(base_url: str, api_key: str) -> list[str]:
    """
    获取OpenAI兼容API的可用模型列表
    
    调用/v1/models端点获取模型列表，解析并返回模型ID列表。
    
    Args:
        base_url: API基础URL
        api_key: API密钥
    
    Returns:
        list[str]: 模型ID列表，按字母顺序排序并去重。如果请求失败返回空列表
    """
    url = _normalize_base_url(base_url) + "/models"
    headers = {"Accept": "application/json", **_auth_headers(api_key)}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            if r.status_code >= 400:
                return []
            data = r.json()
            items = data.get("data") or []
            out: list[str] = []
            for it in items:
                mid = it.get("id")
                if isinstance(mid, str):
                    out.append(mid)
            return sorted(list(set(out)))
    except Exception:
        return []


@dataclass(frozen=True)
class ChatCompletionDelta:
    """
    聊天完成流式响应增量数据
    
    表示流式响应中的单个文本增量。
    
    主要属性：
        text: 增量文本内容
    """
    text: str


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
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
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

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return ChatCompletionResult(text="")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
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
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
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
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return ChatCompletionMessage(role=None, content=None, reasoning_content=None, tool_calls=None)
        message = choices[0].get("message") or {}
        return ChatCompletionMessage(
            role=message.get("role"),
            content=message.get("content"),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=message.get("tool_calls"),
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
) -> AsyncIterator[ChatCompletionDelta]:
    """
    OpenAI兼容的流式聊天完成调用
    
    调用/v1/chat/completions端点，启用流式输出，解析Server-Sent Events (SSE)格式的响应。
    兼容常见的data: {...}行格式和data: [DONE]结束标记。
    
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
    
    Yields:
        ChatCompletionDelta: 流式响应中的文本增量
    
    Raises:
        httpx.HTTPStatusError: HTTP请求失败时抛出
    """
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
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

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    obj = json.loads(data_str)
                except Exception:
                    continue

                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0] or {}).get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    yield ChatCompletionDelta(text=text)
