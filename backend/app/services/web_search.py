"""
主聊天网络搜索：Tavily Search、博查 Bocha Web Search。

仅调用各厂商官方 REST，不做通用 HTML 抓取。
成功返回 {ok:true, code, result}；失败返回 {ok:false, code, message, ...}，不再把错误伪装成检索正文。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.services.http_client import get_async_http_client, get_sync_http_client

from app.schemas import Settings, WebSearchSettings

OPENAI_WEB_SEARCH_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "在互联网上检索最新事实、新闻或可核验资料。当用户询问近期事件、需要查证的数据、"
                "或超出模型知识截止的内容时使用。query 使用与用户相同的语言，简洁明确。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或问句。",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


def web_search_is_configured(settings: Settings) -> bool:
    ws = getattr(settings, "webSearch", None)
    if ws is None:
        return False
    if ws.provider == "tavily":
        t = ws.tavily
        return bool(t and (t.apiKey or "").strip())
    if ws.provider == "bocha":
        b = ws.bocha
        return bool(b and (b.apiKey or "").strip())
    return False


def _search_ok(result: str, *, provider: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "code": "OK", "result": result}
    if provider:
        out["provider"] = provider
    return out


def _search_err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "code": code, "message": message}
    out.update(extra)
    return out


def format_web_search_tool_content(payload: dict[str, Any]) -> str:
    """供 generate tool message：成功用 markdown，失败用结构化 JSON。"""
    if payload.get("ok"):
        return str(payload.get("result") or "")
    return json.dumps(payload, ensure_ascii=False)


def _format_tavily_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    ans = data.get("answer")
    if isinstance(ans, str) and ans.strip():
        lines.append("### 摘要")
        lines.append(ans.strip())
    results = data.get("results") or []
    if results:
        lines.append("### 检索结果")
        for i, it in enumerate(results[:20], 1):
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "")
            url = str(it.get("url") or "")
            content = str(it.get("content") or "")
            lines.append(f"{i}. **{title}**\n   {url}\n   {content}")
    if not lines:
        return json.dumps(data, ensure_ascii=False)[:12000]
    return "\n\n".join(lines)


def _format_bocha_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    pages = data.get("webPages")
    if isinstance(pages, dict):
        items = pages.get("value") or []
    else:
        items = []
    if isinstance(items, list):
        for i, it in enumerate(items[:50], 1):
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "")
            url = str(it.get("url") or "")
            snippet = str(it.get("snippet") or it.get("summary") or "")
            lines.append(f"{i}. **{name}**\n   {url}\n   {snippet}")
    if not lines:
        return json.dumps(data, ensure_ascii=False)[:12000]
    return "\n\n".join(lines)


def _tavily_request(ws: WebSearchSettings, query: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    t = ws.tavily
    api_key = ((t.apiKey if t else None) or "").strip()
    body: dict[str, Any] = {"query": query}
    if t:
        for k, v in t.model_dump(exclude_none=True).items():
            if k == "apiKey":
                continue
            body[k] = v
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return "https://api.tavily.com/search", headers, body


async def _tavily_search(ws: WebSearchSettings, query: str) -> dict[str, Any]:
    url, headers, body = _tavily_request(ws, query)
    client = get_async_http_client()
    r = await client.post(url, json=body, headers=headers, timeout=90.0)
    r.raise_for_status()
    data = r.json()
    return _search_ok(_format_tavily_markdown(data if isinstance(data, dict) else {}), provider="tavily")


def _bocha_request(ws: WebSearchSettings, query: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    b = ws.bocha
    api_key = ((b.apiKey if b else None) or "").strip()
    base = ((b.baseUrl if b and b.baseUrl else None) or "https://api.bocha.cn").rstrip("/")
    body: dict[str, Any] = {"query": query}
    if b:
        for k, v in b.model_dump(exclude_none=True).items():
            if k in ("apiKey", "baseUrl"):
                continue
            body[k] = v
    url = f"{base}/v1/web-search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return url, headers, body


def _parse_bocha_response(status_code: int, text: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _search_err(
            "web_search_invalid_response",
            "博查返回了无效响应",
            provider="bocha",
            detail="response is not an object",
            status=status_code,
        )

    code = data.get("code")
    if status_code == 403 or code == 403 or code == "403":
        msg = data.get("message") or data.get("msg") or "403"
        return _search_err(
            "web_search_quota",
            "余额不足或无权访问（403）",
            provider="bocha",
            detail=str(msg),
            status=403,
        )
    if code != 200 and code != "200":
        msg = data.get("msg") or data.get("message") or str(data)
        return _search_err(
            "web_search_provider_error",
            str(msg),
            provider="bocha",
            status=status_code,
        )

    inner = data.get("data")
    if not isinstance(inner, dict):
        inner = {}
    return _search_ok(_format_bocha_markdown(inner), provider="bocha")


async def _bocha_search(ws: WebSearchSettings, query: str) -> dict[str, Any]:
    url, headers, body = _bocha_request(ws, query)
    client = get_async_http_client()
    r = await client.post(url, json=body, headers=headers, timeout=90.0)
    text = r.text
    try:
        data = r.json()
    except json.JSONDecodeError:
        return _search_err(
            "web_search_invalid_response",
            f"HTTP {r.status_code}：响应不是合法 JSON",
            provider="bocha",
            detail=text[:2000],
            status=r.status_code,
        )
    return _parse_bocha_response(r.status_code, text, data)


def _map_http_status_error(exc: httpx.HTTPStatusError, *, provider: str | None) -> dict[str, Any]:
    try:
        detail = (exc.response.text or "")[:2000]
    except Exception:
        detail = ""
    status = exc.response.status_code
    code = "web_search_quota" if status == 403 else "web_search_http_error"
    return _search_err(
        code,
        f"HTTP {status}",
        provider=provider,
        detail=detail,
        status=status,
    )


async def run_web_search(settings: Settings, query: str) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return _search_err("web_search_empty_query", "空查询")
    ws = settings.webSearch
    if ws is None or not web_search_is_configured(settings):
        return _search_err("web_search_not_configured", "未配置网络搜索或缺少 API Key")
    provider = ws.provider
    try:
        if provider == "tavily":
            return await _tavily_search(ws, q)
        if provider == "bocha":
            return await _bocha_search(ws, q)
    except httpx.HTTPStatusError as e:
        return _map_http_status_error(e, provider=provider)
    except Exception as e:
        return _search_err(
            "web_search_provider_error",
            str(e) or "网络搜索失败",
            provider=provider,
        )
    return _search_err("web_search_unknown_provider", "未知提供方", provider=provider)


def run_web_search_sync(settings: Settings, query: str) -> dict[str, Any]:
    """同步版本，供现有同步 assistant tool executor 调用。"""
    q = (query or "").strip()
    if not q:
        return _search_err("web_search_empty_query", "空查询")
    ws = settings.webSearch
    if ws is None or not web_search_is_configured(settings):
        return _search_err("web_search_not_configured", "未配置网络搜索或缺少 API Key")
    provider = ws.provider
    try:
        client = get_sync_http_client()
        if provider == "tavily":
            url, headers, body = _tavily_request(ws, q)
            r = client.post(url, json=body, headers=headers, timeout=90.0)
            r.raise_for_status()
            data = r.json()
            return _search_ok(
                _format_tavily_markdown(data if isinstance(data, dict) else {}),
                provider="tavily",
            )
        if provider == "bocha":
            url, headers, body = _bocha_request(ws, q)
            r = client.post(url, json=body, headers=headers, timeout=90.0)
            text = r.text
            try:
                data = r.json()
            except json.JSONDecodeError:
                return _search_err(
                    "web_search_invalid_response",
                    f"HTTP {r.status_code}：响应不是合法 JSON",
                    provider="bocha",
                    detail=text[:2000],
                    status=r.status_code,
                )
            return _parse_bocha_response(r.status_code, text, data)
    except httpx.HTTPStatusError as e:
        return _map_http_status_error(e, provider=provider)
    except Exception as e:
        return _search_err(
            "web_search_provider_error",
            str(e) or "网络搜索失败",
            provider=provider,
        )
    return _search_err("web_search_unknown_provider", "未知提供方", provider=provider)


async def fetch_tavily_usage(api_key: str) -> dict[str, Any]:
    key = api_key.strip()
    if not key:
        return {"ok": False, "error": "empty key"}
    url = "https://api.tavily.com/usage"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    client = get_async_http_client()
    r = await client.get(url, headers=headers, timeout=20.0)
    try:
        data = r.json()
    except json.JSONDecodeError:
        data = {"raw": (r.text or "")[:2000]}
    if r.status_code >= 400:
        msg = f"HTTP {r.status_code}"
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, dict):
                err = detail.get("error")
                if isinstance(err, str) and err.strip():
                    msg = err.strip()
        return {"ok": False, "status": r.status_code, "message": msg}
    return {"ok": True, "data": data if isinstance(data, dict) else {"value": data}}


async def fetch_bocha_remaining(api_key: str, base_url: str | None) -> dict[str, Any]:
    key = api_key.strip()
    if not key:
        return {"ok": False, "error": "empty key"}
    base = (base_url or "https://api.bocha.cn").rstrip("/")
    url = f"{base}/v1/fund/remaining"
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    client = get_async_http_client()
    r = await client.get(url, headers=headers, timeout=20.0)
    try:
        data = r.json()
    except json.JSONDecodeError:
        data = {"raw": (r.text or "")[:2000]}
    if r.status_code >= 400:
        msg = f"HTTP {r.status_code}"
        if isinstance(data, dict):
            m = data.get("msg")
            if isinstance(m, str) and m.strip():
                msg = m.strip()
        return {"ok": False, "status": r.status_code, "message": msg}
    inner = data.get("data") if isinstance(data, dict) else {}
    remaining = None
    if isinstance(inner, dict):
        remaining = inner.get("remaining")
    return {"ok": True, "remaining": remaining}
