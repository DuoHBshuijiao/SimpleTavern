"""网络搜索用量/余额代理（避免前端直连第三方）。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.web_search import fetch_bocha_remaining, fetch_tavily_usage
from app.storage import load_settings

router = APIRouter()

async def _quota_status(provider: str, request: Awaitable[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    try:
        return provider, await request
    except Exception:
        return provider, {"ok": False, "message": f"{provider} 额度暂时无法查询"}


@router.get("/web-search/status")
async def web_search_status() -> JSONResponse:
    settings = load_settings()
    ws = settings.webSearch
    out: dict[str, Any] = {
        "provider": getattr(ws, "provider", None) if ws else None,
        "tavily": None,
        "bocha": None,
        "brave": None,
        "modes": {
            "independent": ["tavily", "bocha", "brave"],
            "native": ["openai_responses", "anthropic_messages", "gemini_generate_content"],
        },
    }
    if not ws:
        return JSONResponse(out)
    requests = []
    if ws.tavily and (ws.tavily.apiKey or "").strip():
        requests.append(_quota_status("tavily", fetch_tavily_usage(ws.tavily.apiKey)))
    if ws.bocha and (ws.bocha.apiKey or "").strip():
        requests.append(_quota_status("bocha", fetch_bocha_remaining(ws.bocha.apiKey, ws.bocha.baseUrl)))
    out.update(await asyncio.gather(*requests))
    brave = getattr(ws, "brave", None)
    if brave and (brave.apiKey or "").strip():
        out["brave"] = {
            "ok": True,
            "configured": True,
            "message": "Brave Search 无公开余额查询接口；已配置 Subscription Token。",
        }
    return JSONResponse(out)
