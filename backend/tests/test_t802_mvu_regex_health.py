from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.content_regex_queue import (
    clear_queue,
    enqueue_content_regex_items,
    get_content_regex_queue_dropped,
    get_content_regex_queue_size,
    reset_content_regex_queue_dropped,
)
from app.content_regex_scanner import get_content_regex_scanner_health
from app.errors import AppError, install_error_handlers
from app.group_mvu import MvuRuntimeEnablement, resolve_chat_mvu_runtime_enablement
from app.request_context import RequestIdMiddleware
from app.routes import mvu as mvu_routes
from app.routes.generate import match_worldbook_entries
from app.schemas import Chat, ChatOverrides, WorldBook, WorldBookEntry
from app.services import mvu_daemon
from app.services.assistant_agent import _parse_tool_call_arguments
from app.services.knowledge_graph import KnowledgeGraphError, _require_mvu_enabled
from app.services.mvu_agent import MvuAgentEvent


def test_resolve_group_mvu_enabled_requires_readable_character() -> None:
    chat = Chat(
        id="g1",
        characterId="anchor-char",
        title="group",
        messages=[],
        isGroup=True,
        overrides=ChatOverrides(groupMvuEnabled=True),
    )
    with patch("app.storage.load_character", side_effect=AppError(
        code="data_corrupted",
        message="角色卡文件已损坏或结构无效",
        source="storage.character",
        status_code=500,
    )):
        result = resolve_chat_mvu_runtime_enablement(chat)
    assert result.enabled is False
    assert result.character_error is not None
    assert result.character_error.code == "mvu_character_unreadable"


def test_ensure_mvu_worker_maps_corrupted_character_to_enable_error() -> None:
    chat = Chat(
        id="g2",
        characterId="anchor-char",
        title="group",
        messages=[],
        isGroup=True,
        overrides=ChatOverrides(groupMvuEnabled=True),
    )
    mvu_daemon._health.pop(chat.id, None)
    with patch("app.services.mvu_daemon.load_chat", return_value=chat):
        with patch(
            "app.services.mvu_daemon.resolve_chat_mvu_runtime_enablement",
            return_value=MvuRuntimeEnablement(enabled=True),
        ):
            with patch(
                "app.services.mvu_daemon.load_character",
                side_effect=AppError(
                    code="data_corrupted",
                    message="角色卡文件已损坏或结构无效",
                    source="storage.character",
                    status_code=500,
                ),
            ):
                ok = mvu_daemon.ensure_mvu_worker(chat.id)
    assert ok is False
    health = mvu_daemon.get_mvu_worker_health(chat.id)
    assert health["enableError"] is not None
    assert health["enableError"]["code"] == "mvu_character_unreadable"


def test_match_worldbook_budget_pass_does_not_collect_warnings() -> None:
    """预算阶段不传 warnings_out；最终注入只收集一次。"""
    entry = WorldBookEntry.model_construct(
        id="e1",
        regex="[unterminated",
        content="x",
        enabled=True,
        orderIndex=0,
    )
    book = WorldBook.model_construct(id="wb1", name="book", entries=[entry])
    warnings: list[dict] = []
    match_worldbook_entries(book, [{"role": "user", "content": "hi"}], 5)
    match_worldbook_entries(book, [{"role": "user", "content": "hi"}], 5, warnings_out=warnings)
    assert len(warnings) == 1
    assert warnings[0]["code"] == "worldbook_regex_invalid"


def test_resolve_chat_mvu_runtime_enablement_character_unreadable() -> None:
    chat = Chat(id="c1", characterId="missing-char", title="t", messages=[])
    with patch("app.storage.load_character", side_effect=FileNotFoundError("gone")):
        result = resolve_chat_mvu_runtime_enablement(chat)
    assert result.enabled is False
    assert result.character_error is not None
    assert result.character_error.code == "mvu_character_unreadable"


def test_require_mvu_enabled_surfaces_character_unreadable() -> None:
    chat = Chat(id="c1", characterId="missing-char", title="t", messages=[])
    enablement = MvuRuntimeEnablement(
        enabled=False,
        character_error=AppError(
            code="mvu_character_unreadable",
            message="角色不可读",
            source="test",
            status_code=500,
        ),
    )
    with patch("app.services.knowledge_graph.load_chat", return_value=chat):
        with patch(
            "app.services.knowledge_graph.resolve_chat_mvu_runtime_enablement",
            return_value=enablement,
        ):
            with pytest.raises(KnowledgeGraphError) as exc_info:
                _require_mvu_enabled("c1")
    assert exc_info.value.code == "mvu_character_unreadable"
    assert exc_info.value.status_code == 500


def test_content_regex_queue_counts_dropped_items() -> None:
    chat_id = "queue-drop-count"
    clear_queue(chat_id)
    reset_content_regex_queue_dropped(chat_id)
    stats = enqueue_content_regex_items(chat_id, [{"value": str(i)} for i in range(505)])
    assert stats["enqueued"] == 505
    assert stats["dropped"] == 5
    assert get_content_regex_queue_size(chat_id) == 500
    assert get_content_regex_queue_dropped(chat_id) == 5
    clear_queue(chat_id)
    reset_content_regex_queue_dropped(chat_id)


@pytest.mark.asyncio
async def test_mvu_broadcast_counts_queue_full() -> None:
    chat_id = "sse-drop-chat"
    mvu_daemon._sse_dropped.pop(chat_id, None)
    q = asyncio.Queue(maxsize=1)
    mvu_daemon._subscribers[chat_id] = [q]
    await mvu_daemon._broadcast(chat_id, MvuAgentEvent("log_entry", {"id": "1"}))
    await mvu_daemon._broadcast(chat_id, MvuAgentEvent("log_entry", {"id": "2"}))
    assert mvu_daemon._sse_dropped.get(chat_id, 0) >= 1
    mvu_daemon._subscribers.pop(chat_id, None)
    mvu_daemon._sse_dropped.pop(chat_id, None)


def test_mvu_agent_parse_rejects_invalid_json() -> None:
    args, err = _parse_tool_call_arguments(
        {"function": {"name": "mvu_update_cell", "arguments": "{bad"}},
        "mvu_update_cell",
    )
    assert args is None
    assert err is not None
    assert err["code"] == "tool_call_invalid"


def test_match_worldbook_entries_emits_regex_warning() -> None:
    entry = WorldBookEntry.model_construct(
        id="e1",
        regex="[unterminated",
        content="x",
        enabled=True,
        orderIndex=0,
    )
    book = WorldBook.model_construct(id="wb1", name="book", entries=[entry])
    warnings: list[dict] = []
    matched = match_worldbook_entries(book, [{"role": "user", "content": "hi"}], 5, warnings_out=warnings)
    assert matched == []
    assert len(warnings) == 1
    assert warnings[0]["code"] == "worldbook_regex_invalid"


def test_health_endpoints_exist(monkeypatch) -> None:
    chat = Chat(id="health-chat", characterId="char1", title="t", messages=[], overrides=ChatOverrides())
    monkeypatch.setattr(mvu_routes, "load_chat", lambda _cid: chat)
    monkeypatch.setattr(mvu_daemon, "ensure_mvu_worker", lambda _cid: False)
    monkeypatch.setattr(mvu_daemon, "get_mvu_worker_health", lambda _cid: {"status": "disabled", "enabled": False})

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(mvu_routes.router, prefix="/api")
    with TestClient(app) as client:
        mvu = client.get("/api/mvu/health-chat/health")
        assert mvu.status_code == 200
        assert "health" in mvu.json()
        regex = client.get("/api/content-regex/health")
        assert regex.status_code == 200
        assert "health" in regex.json()
        assert "status" in get_content_regex_scanner_health()
