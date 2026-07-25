"""Assistant web search tool handler."""

from __future__ import annotations

from app.assistant_tools import result as R
from app.assistant_tools.context import AssistantToolContext
from app.services.web_search import run_web_search_sync, web_search_is_configured
from app.storage import load_settings


def handle_web_search(ctx: AssistantToolContext, args: dict[str, object]) -> dict[str, object]:
    if not ctx.allow_web_search:
        return R.err(R.FORBIDDEN, "web search not enabled for this request", tool="web_search")
    settings = load_settings()
    if not web_search_is_configured(settings):
        return R.err(R.VALIDATION_ERROR, "web search provider is not configured", tool="web_search")
    query = str(args.get("query") or "").strip()
    if not query:
        return R.err(R.VALIDATION_ERROR, "query is required", tool="web_search")
    payload = run_web_search_sync(settings, query)
    if not payload.get("ok"):
        return R.err(
            str(payload.get("code") or "web_search_provider_error"),
            str(payload.get("message") or "网络搜索失败"),
            tool="web_search",
            details={k: v for k, v in payload.items() if k not in {"ok", "code", "message"}},
        )
    return R.ok(
        {
            "provider": payload.get("provider")
            or (settings.webSearch.provider if settings.webSearch else None),
            "query": query,
            "result": payload.get("result") or "",
        },
        tool="web_search",
    )
