"""网络搜索用量/余额代理（避免前端直连第三方）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.web_search import fetch_bocha_remaining, fetch_tavily_usage
from app.storage import load_settings

router = APIRouter()


@router.get("/web-search/status")
async def web_search_status() -> JSONResponse:
    settings = load_settings()
    ws = settings.webSearch
    out: dict[str, Any] = {"provider": getattr(ws, "provider", None) if ws else None, "tavily": None, "bocha": None}
    if not ws:
        return JSONResponse(out)
    if ws.tavily and (ws.tavily.apiKey or "").strip():
        out["tavily"] = await fetch_tavily_usage(ws.tavily.apiKey)
    if ws.bocha and (ws.bocha.apiKey or "").strip():
        out["bocha"] = await fetch_bocha_remaining(ws.bocha.apiKey, ws.bocha.baseUrl if ws.bocha else None)
    return JSONResponse(out)
