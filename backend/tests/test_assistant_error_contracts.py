from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.executor import execute_tool
from app.errors import AppError, install_error_handlers
from app.request_context import RequestIdMiddleware
from app.routes import assistant as assistant_routes
from app.schemas import AssistantChat, AssistantSettings, CharacterCard, ChatMessage
from app.services.assistant_agent import (
    AssistantAgentRunContext,
    AssistantAgentService,
    _parse_tool_call_arguments,
)


def _tool_ctx() -> AssistantToolContext:
    return AssistantToolContext(
        chat_id=None,
        scope="workspace",
        allow_write_memory=False,
        allow_destructive_tools=False,
        allow_web_search=False,
        assistant_settings=AssistantSettings(),
    )


def test_normalize_assistant_chat_rejects_invalid_tool_message() -> None:
    dirty = ChatMessage.model_construct(role="tool", content="{}", tool_call_id="")
    chat = AssistantChat.model_construct(messages=[dirty])
    with pytest.raises(AppError) as exc_info:
        assistant_routes._normalize_assistant_chat_for_save(chat)
    assert exc_info.value.code == "assistant_message_invalid"
    assert exc_info.value.status_code == 400


def test_parse_tool_call_arguments_rejects_invalid_json() -> None:
    args, err = _parse_tool_call_arguments(
        {"function": {"name": "workspace_list_files", "arguments": "{not-json"}},
        "workspace_list_files",
    )
    assert args is None
    assert err is not None
    assert err["ok"] is False
    assert err["code"] == "tool_call_invalid"


def test_parse_tool_call_arguments_accepts_object() -> None:
    args, err = _parse_tool_call_arguments(
        {"function": {"name": "workspace_list_files", "arguments": '{"path":"."}'}},
        "workspace_list_files",
    )
    assert err is None
    assert args == {"path": "."}


def test_execute_tool_rejects_non_dict_args() -> None:
    outcome = execute_tool("workspace_list_files", ["bad"], _tool_ctx())  # type: ignore[arg-type]
    assert outcome.result["ok"] is False
    assert outcome.result["code"] == "VALIDATION_ERROR"
    assert outcome.result["details"]["kind"] == "tool_call_invalid"


@pytest.mark.asyncio
async def test_agent_stream_maps_exception_to_envelope() -> None:
    chat = AssistantChat(messages=[])

    async def _boom(**_kwargs):
        raise RuntimeError("upstream exploded")
        yield  # pragma: no cover

    ctx = AssistantAgentRunContext(
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        temperature=0.2,
        messages=[{"role": "user", "content": "hi"}],
        extra_body={},
        tool_ctx=_tool_ctx(),
        load_chat=lambda: chat,
        save_chat=lambda c: c,
        max_tool_turns=2,
    )
    agent = AssistantAgentService(ctx)
    with patch("app.services.assistant_agent.stream_chat_completions", _boom):
        events = [event async for event in agent.iter_events()]
    assert len(events) == 1
    assert events[0].kind == "error"
    assert events[0].data["code"] == "assistant_failed"
    assert events[0].data["terminal"] is True
    assert "requestId" in events[0].data
    assert "exploded" in (events[0].data.get("detail") or events[0].data.get("message") or "")


@pytest.mark.asyncio
async def test_agent_nonstream_raises_app_error() -> None:
    chat = AssistantChat(messages=[])

    async def _boom(**_kwargs):
        raise RuntimeError("nonstream boom")

    ctx = AssistantAgentRunContext(
        base_url="https://example.test/v1",
        api_key="k",
        model="m",
        temperature=0.2,
        messages=[{"role": "user", "content": "hi"}],
        extra_body={},
        tool_ctx=_tool_ctx(),
        load_chat=lambda: chat,
        save_chat=lambda c: c,
        max_tool_turns=2,
    )
    agent = AssistantAgentService(ctx)
    with patch("app.services.assistant_agent.chat_completions_message", _boom):
        with pytest.raises(AppError) as exc_info:
            await agent.run_nonstream()
    assert exc_info.value.code == "assistant_failed"


def test_workspace_character_card_missing_and_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    card_path = tmp_path / "character_card.json"
    monkeypatch.setattr(assistant_routes, "workspace_character_card_path", lambda: card_path)

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(assistant_routes.router, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.get("/api/assistant/workspace/character-card")
        assert missing.status_code == 404
        body = missing.json()
        assert body["code"] == "data_not_found"
        assert "requestId" in body

        card_path.write_text("{not-json", encoding="utf-8")
        corrupt = client.get("/api/assistant/workspace/character-card")
        assert corrupt.status_code == 500
        corrupt_body = corrupt.json()
        assert corrupt_body["code"] == "data_corrupted"

        valid = CharacterCard(name="测试角色", description="d")
        card_path.write_text(json.dumps(valid.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
        ok = client.get("/api/assistant/workspace/character-card")
        assert ok.status_code == 200
        assert ok.json()["name"] == "测试角色"


def test_assistant_route_no_legacy_ok_false_character_card() -> None:
    source = Path(assistant_routes.__file__).read_text(encoding="utf-8")
    assert '{"ok": False, "error": "not found"' not in source
    assert 'return {"ok": False, "error": str(exc)' not in source
