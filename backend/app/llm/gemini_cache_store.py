"""Gemini 显式 cachedContents 索引（T-821）。

把稳定前缀（systemInstruction + tools + 模型）做成硬盘索引 ``data/llm_cache_index.json``。
命中则 generateContent 只传 ``cachedContent`` 名称；404 时重建一次。
创建失败必须结构化报错，不得静默退回无缓存。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.errors import AppError, as_app_error
from app.llm.prompt_cache import PromptCachePlan, gemini_cache_ttl_seconds
from app.llm.types import append_query_key, auth_headers_for_style
from app.services.http_client import get_async_http_client
from app.services.http_log import log_outbound
from app.storage import _data_dir

_INDEX_NAME = "llm_cache_index.json"
_PROVIDER = "gemini"


def _index_path() -> Path:
    return _data_dir() / _INDEX_NAME


def fingerprint(*, model: str, system_instruction: Any, tools: Any) -> str:
    blob = json.dumps(
        {"model": model, "system": system_instruction, "tools": tools},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _load_index() -> dict[str, Any]:
    path = _index_path()
    if not path.is_file():
        return {"entries": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": {}}
    if not isinstance(raw, dict):
        return {"entries": {}}
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        raw["entries"] = {}
    return raw


def _save_index(index: dict[str, Any]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def lookup(fp: str) -> str | None:
    entries = _load_index().get("entries") or {}
    item = entries.get(fp)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(item, str) and item.strip():
        return item.strip()
    return None


def remember(fp: str, name: str, *, model: str, ttl_seconds: int) -> None:
    index = _load_index()
    entries = index.setdefault("entries", {})
    entries[fp] = {
        "name": name,
        "model": model,
        "ttlSeconds": ttl_seconds,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    _save_index(index)


def forget(fp: str) -> None:
    index = _load_index()
    entries = index.get("entries")
    if isinstance(entries, dict) and fp in entries:
        entries.pop(fp, None)
        _save_index(index)


def _cache_error(message: str, *, detail: str | None = None, status_code: int = 502) -> AppError:
    return AppError(
        code="gemini_cache_failed",
        message=message,
        source="llm.gemini.cached_contents",
        status_code=status_code,
        detail=detail,
        provider=_PROVIDER,
        protocol="gemini_generate_content",
        suggested_action="检查 Gemini API Key 与 cachedContents 权限，或把缓存模式改为隐式/关闭",
    )


async def create_cached_content(
    *,
    api_root: str,
    api_key: str,
    model: str,
    system_instruction: Any,
    tools: Any,
    ttl_seconds: int,
    extra_headers: dict[str, str] | None = None,
    auth_style: str | None = None,
) -> str:
    model_id = model[len("models/") :] if model.startswith("models/") else model
    style = auth_style or "x-goog-api-key"
    url = append_query_key(f"{api_root.rstrip('/')}/cachedContents", api_key, style)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **auth_headers_for_style(api_key, style),
        **(extra_headers or {}),
    }
    body: dict[str, Any] = {
        "model": f"models/{model_id}",
        "ttl": f"{int(ttl_seconds)}s",
    }
    if system_instruction is not None:
        body["systemInstruction"] = system_instruction
    if tools is not None:
        body["tools"] = tools
    try:
        async with log_outbound(
            source="llm",
            method="POST",
            url=url,
            request_headers=headers,
            request_body=body,
            streaming=False,
        ) as _log:
            client = get_async_http_client()
            r = await client.post(url, headers=headers, json=body, timeout=60)
            _log.set_response(status=r.status_code, headers=dict(r.headers), text=r.text)
            if r.status_code >= 400:
                raise _cache_error(
                    "创建 Gemini 显式缓存失败",
                    detail=f"HTTP {r.status_code}: {(r.text or '')[:800]}",
                    status_code=502 if r.status_code >= 500 else 400,
                )
            data = r.json()
    except AppError:
        raise
    except Exception as exc:
        raise as_app_error(
            exc,
            source="llm.gemini.cached_contents",
            default_code="gemini_cache_failed",
            default_message="创建 Gemini 显式缓存失败",
            default_status_code=502,
            provider=_PROVIDER,
            protocol="gemini_generate_content",
        ) from exc
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise _cache_error("Gemini cachedContents 响应缺少 name", detail=str(data)[:400])
    return name.strip()


async def attach_explicit_cache(
    payload: dict[str, Any],
    *,
    plan: PromptCachePlan | None,
    api_root: str,
    api_key: str,
    model: str,
    extra_headers: dict[str, str] | None = None,
    auth_style: str | None = None,
) -> dict[str, Any]:
    """显式模式：确保 cachedContents 存在并挂到 payload；隐式/关闭不改写。"""
    ttl = gemini_cache_ttl_seconds(plan)
    if ttl is None or plan is None or plan.mode != "explicit":
        return payload
    system = payload.get("systemInstruction")
    tools = payload.get("tools")
    if system is None and tools is None:
        return payload
    fp = fingerprint(model=model, system_instruction=system, tools=tools)
    name = lookup(fp)
    if name is None:
        name = await create_cached_content(
            api_root=api_root,
            api_key=api_key,
            model=model,
            system_instruction=system,
            tools=tools,
            ttl_seconds=ttl,
            extra_headers=extra_headers,
            auth_style=auth_style,
        )
        remember(fp, name, model=model, ttl_seconds=ttl)
    out = dict(payload)
    out["cachedContent"] = name
    # 已缓存的稳定前缀不再随 generateContent 重复计费写入
    out.pop("systemInstruction", None)
    out.pop("tools", None)
    return out


def is_cached_content_not_found(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code == 404:
        text = (exc.response.text or "").lower()
        return "cachedcontent" in text or "cached content" in text or "not found" in text
    if isinstance(exc, AppError):
        detail = (exc.detail or "").lower()
        return exc.upstream_status == 404 and ("cachedcontent" in detail or "cached content" in detail)
    return False


def forget_cached_name(name: str) -> None:
    index = _load_index()
    entries = index.get("entries")
    if not isinstance(entries, dict):
        return
    drop = [k for k, v in entries.items() if (v.get("name") if isinstance(v, dict) else v) == name]
    for k in drop:
        entries.pop(k, None)
    if drop:
        _save_index(index)


__all__ = [
    "attach_explicit_cache",
    "create_cached_content",
    "fingerprint",
    "forget",
    "forget_cached_name",
    "is_cached_content_not_found",
    "lookup",
    "remember",
]
