from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


def _normalize_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    # 允许用户填到 /v1，也允许只填域名；统一为包含 /v1
    if base.endswith("/v1"):
        return base
    return base + "/v1"


def _auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


async def list_models_openai_compat(base_url: str, api_key: str) -> list[str]:
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
    text: str


@dataclass(frozen=True)
class ChatCompletionResult:
    text: str


async def chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> ChatCompletionResult:
    """
    OpenAI 兼容 `/v1/chat/completions` 的非流式调用。
    """
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

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


async def stream_chat_completions(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[ChatCompletionDelta]:
    """
    OpenAI 兼容 `/v1/chat/completions` 的 `stream=true` 输出解析。
    兼容常见的 `data: {...}` 行与 `data: [DONE]` 结束标记。
    """
    url = _normalize_base_url(base_url) + "/chat/completions"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

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


