"""网络搜索配置与结果格式化单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.handlers.web_search import handle_web_search
from app.assistant_tools.registry import build_openai_tools_list
from app.schemas import AssistantSettings, Settings, WebSearchSettings, WebSearchTavilySettings
from app.services.web_search import (
    _format_tavily_markdown,
    _tavily_request,
    format_web_search_tool_content,
    run_web_search_sync,
    web_search_is_configured,
)


def test_web_search_is_configured_false_when_missing() -> None:
    s = Settings()
    assert web_search_is_configured(s) is False


def test_web_search_is_configured_tavily_key() -> None:
    s = Settings(
        webSearch=WebSearchSettings(
            provider="tavily",
            tavily=WebSearchTavilySettings(apiKey="tvly-test"),
        ),
    )
    assert web_search_is_configured(s) is True


def test_format_tavily_markdown_basic() -> None:
    md = _format_tavily_markdown(
        {
            "answer": "short answer",
            "results": [
                {"title": "T", "url": "https://x.test", "content": "snippet"},
            ],
        },
    )
    assert "摘要" in md
    assert "short answer" in md
    assert "https://x.test" in md


def test_tavily_search_uses_bearer_header_not_body_key() -> None:
    ws = WebSearchSettings(
        provider="tavily",
        tavily=WebSearchTavilySettings(apiKey="tvly-test", max_results=3),
    )
    _url, headers, body = _tavily_request(ws, "query")
    assert headers["Authorization"] == "Bearer tvly-test"
    assert body["query"] == "query"
    assert body["max_results"] == 3
    assert "api_key" not in body


def test_assistant_web_search_tool_requires_toggle() -> None:
    base_ctx = AssistantToolContext(
        chat_id="chat-1",
        scope="chat",
        allow_write_memory=False,
        allow_destructive_tools=False,
        allow_web_search=False,
        assistant_settings=AssistantSettings(),
    )
    disabled_names = {tool["function"]["name"] for tool in build_openai_tools_list(base_ctx)}
    assert "web_search" not in disabled_names

    enabled_ctx = AssistantToolContext(
        chat_id="chat-1",
        scope="chat",
        allow_write_memory=False,
        allow_destructive_tools=False,
        allow_web_search=True,
        assistant_settings=AssistantSettings(),
    )
    enabled_names = {tool["function"]["name"] for tool in build_openai_tools_list(enabled_ctx)}
    assert "web_search" in enabled_names


def test_run_web_search_sync_maps_http_error() -> None:
    settings = Settings(
        webSearch=WebSearchSettings(
            provider="tavily",
            tavily=WebSearchTavilySettings(apiKey="tvly-test"),
        ),
    )
    request = httpx.Request("POST", "https://api.tavily.com/search")
    response = httpx.Response(403, request=request, text="quota")
    with patch("app.services.web_search.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post.side_effect = httpx.HTTPStatusError("403", request=request, response=response)
        client_cls.return_value = client
        payload = run_web_search_sync(settings, "hello")
    assert payload["ok"] is False
    assert payload["code"] == "web_search_quota"
    tool_content = format_web_search_tool_content(payload)
    assert "web_search_quota" in tool_content


def test_handle_web_search_returns_tool_result_err_on_provider_failure(monkeypatch) -> None:
    settings = Settings(
        webSearch=WebSearchSettings(
            provider="tavily",
            tavily=WebSearchTavilySettings(apiKey="tvly-test"),
        ),
    )
    monkeypatch.setattr(
        "app.assistant_tools.handlers.web_search.load_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.assistant_tools.handlers.web_search.run_web_search_sync",
        lambda *_a, **_k: {
            "ok": False,
            "code": "web_search_http_error",
            "message": "HTTP 500",
            "provider": "tavily",
        },
    )
    ctx = AssistantToolContext(
        chat_id="chat-1",
        scope="chat",
        allow_write_memory=False,
        allow_destructive_tools=False,
        allow_web_search=True,
        assistant_settings=AssistantSettings(),
    )
    result = handle_web_search(ctx, {"query": "hello"})
    assert result["ok"] is False
    assert result["code"] == "web_search_http_error"
