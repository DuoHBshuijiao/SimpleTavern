"""
Gemini generateContent / streamGenerateContent provider adapter (T-805-5C).

Native Google Generative Language API only — NOT the OpenAI-compatible
`…/v1beta/openai` shim. Tools / functionCall deferred to T-806.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qsl

import httpx

from app.errors import AppError, as_app_error
from app.llm.providers.openai_compatible_chat import (
    STREAM_TEXT_CHUNK_SIZE,
    ChatCompletionMessage,
    ChatCompletionResult,
    StreamChunk,
)
from app.llm.types import (
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    GenerationConfig,
    Usage,
    WireRequest,
)
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound

_PROVIDER = "gemini"
_PROTOCOL = GEMINI_GENERATE_CONTENT_PROTOCOL
_DEFAULT_MAX_TOKENS = 4096
_MAX_ERROR_BODY_CHARS = 12000

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
        source="llm.gemini_generate_content",
        status_code=status_code,
        retryable=retryable,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="检查 Gemini 原生 Base URL（勿用 …/v1beta/openai）与 API Key / 模型",
    )


def _tools_unsupported(*, detail: str) -> AppError:
    return AppError(
        code="provider_capability_unsupported",
        message="当前 Gemini generateContent 适配器尚未支持工具调用",
        detail=detail,
        source="llm.gemini_generate_content",
        status_code=400,
        retryable=False,
        provider=_PROVIDER,
        protocol=_PROTOCOL,
        suggested_action="请改用 OpenAI Compatible Chat，或等待 T-806 工具支持",
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
            status = err.get("status")
            return f"{m.strip()}" + (f" ({status})" if status else "")
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


def _reject_openai_compat_base(base_url: str) -> None:
    lower = (base_url or "").strip().lower()
    if "/openai" in lower:
        raise AppError(
            code="provider_request_invalid",
            message="Gemini 原生协议不能使用 OpenAI 兼容端点",
            detail=f"base_url contains /openai: {base_url!r}",
            source="llm.gemini_generate_content",
            status_code=400,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
            suggested_action=(
                "请将 Base URL 改为 https://generativelanguage.googleapis.com "
                "（或 …/v1beta），或把协议改回 OpenAI Compatible Chat"
            ),
        )


def _api_root(base_url: str) -> str:
    """Normalize to …/v1beta root (no trailing slash)."""
    _reject_openai_compat_base(base_url)
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("API 基础地址未配置或为空。请填写 Gemini Base URL。")
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "https://" + raw
    raw = raw.rstrip("/")
    # Drop accidental action suffixes if user pasted a full generateContent URL.
    for suffix in (":streamGenerateContent", ":generateContent"):
        if suffix.lower() in raw.lower():
            idx = raw.lower().rfind(suffix.lower())
            raw = raw[:idx].rstrip("/")
            # also strip /models/{id}
            if "/models/" in raw.lower():
                raw = raw[: raw.lower().rfind("/models/")].rstrip("/")
            break
    parts = urlsplit(raw)
    path = (parts.path or "").rstrip("/")
    if not path or path == "/":
        path = "/v1beta"
    elif path.endswith("/v1"):
        # Generative Language native surface is v1beta for generateContent.
        path = path[:-3] + "/v1beta"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _model_action_url(base_url: str, *, model: str, stream: bool) -> str:
    root = _api_root(base_url)
    model_id = (model or "").strip()
    if not model_id:
        raise _protocol_error(
            code="config_missing",
            message="未指定 Gemini 模型",
            detail="model is empty",
            status_code=400,
        )
    if model_id.startswith("models/"):
        model_id = model_id[len("models/") :]
    action = "streamGenerateContent" if stream else "generateContent"
    url = f"{root}/models/{model_id}:{action}"
    if stream:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["alt"] = "sse"
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return url


def _models_list_url(base_url: str) -> str:
    return f"{_api_root(base_url)}/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"x-goog-api-key": api_key.strip()}


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
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _to_gemini_parts(content: Any) -> list[dict[str, Any]]:
    if content is None:
        return [{"text": ""}]
    if isinstance(content, str):
        return [{"text": content}]
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    parts.append({"text": item})
                continue
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ in {None, "text"} and isinstance(item.get("text"), str):
                if item["text"]:
                    parts.append({"text": item["text"]})
            elif typ == "image_url":
                raise _protocol_error(
                    code="provider_capability_unsupported",
                    message="当前 Gemini 适配器尚未支持图片输入",
                    detail="image_url content parts are not supported in T-805-5C",
                    status_code=400,
                )
            elif "functionCall" in item or "function_call" in item or typ == "function_call":
                raise _tools_unsupported(detail="functionCall part in messages")
        return parts or [{"text": ""}]
    return [{"text": str(content)}]


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
    if extra.get("tools") or extra.get("functionDeclarations") or extra.get("toolConfig"):
        raise _tools_unsupported(detail="extra_body contains Gemini tool fields")


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    _reject_tools_in_messages(messages)
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []

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
        if role == "assistant":
            gem_role = "model"
        elif role == "user":
            gem_role = "user"
        elif role == "model":
            gem_role = "model"
        else:
            raise _protocol_error(
                code="provider_request_invalid",
                message="消息角色不被 Gemini generateContent 支持",
                detail=f"unsupported role={role!r}",
                status_code=400,
            )
        parts = _to_gemini_parts(content)
        if contents and contents[-1]["role"] == gem_role:
            # Merge consecutive same-role turns.
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": gem_role, "parts": parts})

    system_instruction = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return system_instruction, contents


def _thinking_budget_from_extra(extra_body: dict[str, Any] | None) -> int | None:
    if not extra_body:
        return None
    thinking = extra_body.get("thinking")
    effort = None
    if isinstance(extra_body.get("reasoning"), dict):
        effort = extra_body["reasoning"].get("effort")
    if effort is None:
        effort = extra_body.get("reasoning_effort")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        return _THINKING_BUDGET_BY_EFFORT.get(str(effort or "medium").lower(), 4096)
    # Native Gemini thinkingConfig passthrough handled in generationConfig merge.
    return None


def _build_payload(
    *,
    messages: list[dict[str, Any]],
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    system_instruction, contents = _convert_messages(messages)
    if not contents:
        raise _protocol_error(
            code="provider_request_invalid",
            message="没有可发送给 Gemini 的对话消息",
            detail="contents empty after system extraction",
            status_code=400,
        )

    generation_config: dict[str, Any] = {
        "maxOutputTokens": int(max_tokens) if max_tokens and max_tokens > 0 else _DEFAULT_MAX_TOKENS,
    }
    if temperature is not None:
        generation_config["temperature"] = temperature
    if top_p is not None:
        generation_config["topP"] = top_p

    budget = _thinking_budget_from_extra(extra_body)
    if budget is not None:
        generation_config["thinkingConfig"] = {"thinkingBudget": budget}

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": generation_config,
    }
    if system_instruction is not None:
        payload["systemInstruction"] = system_instruction

    if extra_body:
        for key, value in extra_body.items():
            if key in {
                "thinking",
                "reasoning",
                "reasoning_effort",
                "tools",
                "tool_choice",
                "functionDeclarations",
                "toolConfig",
                "contents",
                "systemInstruction",
            }:
                continue
            if key == "generationConfig" and isinstance(value, dict):
                merged = dict(generation_config)
                merged.update(value)
                # 5C: do not enable cached content helpers from extra.
                merged.pop("cachedContent", None)
                payload["generationConfig"] = merged
                continue
            if key in {"cachedContent", "cache"}:
                continue
            payload[key] = value
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


def _extract_text_and_thoughts(data: dict[str, Any]) -> tuple[str, str | None]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "", None
    first = candidates[0]
    if not isinstance(first, dict):
        return "", None
    # Reject tool calls in native response.
    content = first.get("content")
    if not isinstance(content, dict):
        return "", None
    parts = content.get("parts")
    if not isinstance(parts, list):
        return "", None
    texts: list[str] = []
    thoughts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "functionCall" in part or "function_call" in part:
            raise _tools_unsupported(detail="response contains functionCall")
        text = part.get("text")
        if not isinstance(text, str) or not text:
            continue
        if part.get("thought") is True:
            thoughts.append(text)
        else:
            texts.append(text)
    reasoning = "".join(thoughts).strip() or None
    return "".join(texts), reasoning


def _iter_text_chunks(text: str) -> list[str]:
    if not text:
        return []
    size = max(1, STREAM_TEXT_CHUNK_SIZE)
    return [text[i : i + size] for i in range(0, len(text), size)]


def decode_usage(raw: dict[str, Any] | None) -> Usage | None:
    """Normalize Gemini usageMetadata."""
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

    input_tokens = _as_int(raw.get("promptTokenCount"))
    output_tokens = _as_int(raw.get("candidatesTokenCount"))
    total = _as_int(raw.get("totalTokenCount"))
    cache_read = _as_int(raw.get("cachedContentTokenCount"))
    thoughts = _as_int(raw.get("thoughtsTokenCount"))
    if input_tokens is None and output_tokens is None and total is None and cache_read is None:
        return None
    if total is None and (input_tokens is not None or output_tokens is not None):
        total = (input_tokens or 0) + (output_tokens or 0)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cache_read_input_tokens=cache_read,
        cache_write_input_tokens=None,
        reasoning_tokens=thoughts,
        raw=dict(raw),
    )


async def list_models_gemini(*, base_url: str, api_key: str) -> list[str]:
    url = _models_list_url(base_url)
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
            data = _decode_json_object(r, context="gemini models")
            _log.set_response(body=data)
            raw_models = data.get("models")
            if not isinstance(raw_models, list):
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游服务返回了无效模型列表",
                    detail="models is missing or not a list",
                )
            out: list[str] = []
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                model_id = name.strip()
                if model_id.startswith("models/"):
                    model_id = model_id[len("models/") :]
                # Prefer models that support generateContent when methods listed.
                methods = item.get("supportedGenerationMethods") or item.get("supported_generation_methods")
                if isinstance(methods, list) and methods and "generateContent" not in methods:
                    continue
                out.append(model_id)
            return sorted(set(out))
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.gemini_generate_content.models",
            default_code="provider_request_failed",
            default_message="获取 Gemini 模型列表失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def complete_gemini(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
    as_message: bool = False,
) -> ChatCompletionResult | ChatCompletionMessage:
    _reject_tools_in_config(config)
    url = _model_action_url(base_url, model=config.model, stream=False)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }
    payload = _build_payload(
        messages=messages,
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
            data = _decode_json_object(r, context="gemini generateContent")
            _log.set_response(body=data)
            text, reasoning = _extract_text_and_thoughts(data)
            _ = decode_usage(data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else None)
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
                    detail="gemini generateContent: empty text and thought parts",
                )
            return ChatCompletionResult(text=text)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.gemini_generate_content",
            default_code="provider_request_failed",
            default_message="Gemini 请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


async def stream_gemini(
    *,
    base_url: str,
    api_key: str,
    messages: list[dict[str, Any]],
    config: GenerationConfig,
) -> AsyncIterator[StreamChunk]:
    _reject_tools_in_config(config)
    url = _model_action_url(base_url, model=config.model, stream=True)
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        **_auth_headers(api_key),
    }
    payload = _build_payload(
        messages=messages,
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
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        # Some gateways may emit bare JSON lines; accept objects only.
                        if line.startswith("{"):
                            data_str = line
                        else:
                            raise _protocol_error(
                                code="stream_event_invalid",
                                message="上游流包含未知事件帧",
                                detail=f"unexpected SSE line: {line[:200]}",
                            )
                    else:
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
                    if isinstance(data.get("error"), dict):
                        err = data["error"]
                        raise _protocol_error(
                            code="provider_request_failed",
                            message="Gemini 流式返回错误",
                            detail=str(err.get("message") or err),
                            retryable=True,
                        )
                    usage = data.get("usageMetadata")
                    if isinstance(usage, dict):
                        terminal_usage = usage
                    text, reasoning = _extract_text_and_thoughts(data)
                    if reasoning:
                        saw_output = True
                        aggregated_reasoning.append(reasoning)
                        for piece in _iter_text_chunks(reasoning):
                            yield StreamChunk(kind="reasoning", text=piece)
                    if text:
                        saw_output = True
                        aggregated_content.append(text)
                        for piece in _iter_text_chunks(text):
                            yield StreamChunk(kind="content", text=piece)

            _ = decode_usage(terminal_usage)
            _log.set_response(
                body={
                    "_aggregated": True,
                    "content": "".join(aggregated_content),
                    "reasoning_content": "".join(aggregated_reasoning) or None,
                    "usageMetadata": terminal_usage,
                }
            )
            if not saw_output:
                raise _protocol_error(
                    code="provider_response_invalid",
                    message="上游流未返回任何文本",
                    detail="gemini stream produced no text/thought parts",
                )
            yield StreamChunk(kind="finish", tool_calls=None)
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.gemini_generate_content.stream",
            default_code="provider_request_failed",
            default_message="Gemini 流式请求失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol=_PROTOCOL,
        ) from exc


class GeminiGenerateContentAdapter:
    """ProviderAdapter for Gemini generateContent (no tools in 5C)."""

    provider = _PROVIDER
    protocol = _PROTOCOL

    def validate_config(self, *, base_url: str, api_key: str) -> None:
        if not (base_url or "").strip():
            raise AppError(
                code="config_missing",
                message="API 基础地址未配置",
                source="llm.gemini_generate_content",
                status_code=400,
                suggested_action="填写 https://generativelanguage.googleapis.com 后重试",
                provider=self.provider,
                protocol=self.protocol,
            )
        _reject_openai_compat_base(base_url)
        if not (api_key or "").strip():
            raise AppError(
                code="config_missing",
                message="API Key 未配置",
                source="llm.gemini_generate_content",
                status_code=400,
                suggested_action="在 API 预设中填写 Gemini API Key 后重试",
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
        url = _model_action_url(base_url, model=config.model, stream=bool(config.stream))
        headers = {
            "Accept": "application/json" if not config.stream else "text/event-stream",
            "Content-Type": "application/json",
            **_auth_headers(api_key),
        }
        payload = _build_payload(
            messages=messages,
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
            extra_body=config.extra_body,
        )
        return WireRequest(method="POST", url=url, headers=headers, json_body=payload)

    async def list_models(self, *, base_url: str, api_key: str) -> list[str]:
        self.validate_config(base_url=base_url, api_key=api_key)
        return await list_models_gemini(base_url=base_url, api_key=api_key)

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
        return await complete_gemini(
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
        async for chunk in stream_gemini(
            base_url=base_url,
            api_key=api_key,
            messages=messages,
            config=config,
        ):
            yield chunk

    def decode_usage(self, raw: dict[str, Any] | None) -> Usage | None:
        return decode_usage(raw)
