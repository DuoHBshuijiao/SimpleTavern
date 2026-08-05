from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from unittest.mock import patch

import httpx
from fastapi import Request

from app.errors import AppError
from app.routes.generate import (
    generate_draft_help,
    generate_group_response,
    generate_single_interject,
)
from app.schemas import (
    CharacterCard,
    Chat,
    DraftHelpRequest,
    GroupGenerateRequest,
    Settings,
    SingleInterjectRequest,
)


def _request(path: str, request_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "state": {"request_id": request_id},
        }
    )


async def _failing_stream(**_kwargs):
    upstream_request = httpx.Request(
        "POST",
        "https://provider.example/v1/chat/completions",
    )
    raise httpx.ReadTimeout("timed out", request=upstream_request)
    yield  # pragma: no cover


async def _consume_stream(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def _enter_common_generation_patches(
    stack: ExitStack,
    *,
    chat: Chat,
    character: CharacterCard,
    settings: Settings,
) -> None:
    stack.enter_context(patch("app.routes.generate.load_chat", return_value=chat))
    stack.enter_context(patch("app.routes.generate.load_character", return_value=character))
    stack.enter_context(patch("app.routes.generate.load_settings", return_value=settings))
    stack.enter_context(patch("app.routes.generate.ensure_mvu_worker"))
    stack.enter_context(patch("app.routes.generate.collect_active_worldbooks", return_value=[]))
    stack.enter_context(patch("app.routes.generate.count_tokens", return_value=0))
    stack.enter_context(patch("app.routes.generate.count_tokens_for_messages", return_value=0))
    stack.enter_context(patch("app.routes.generate._inject_mvu_state_tables_for_directive"))
    stack.enter_context(patch("app.routes.generate._inject_knowledge_graph"))
    stack.enter_context(
        patch(
            "app.routes.generate._resolve_generation_credentials",
            return_value=("https://provider.example/v1", "test-key", "openai_compatible_chat", "off"),
        )
    )


def _assert_terminal_error_stream(stream: str, request_id: str) -> None:
    assert stream.index("event: meta") < stream.index("event: error")
    assert f'"requestId": "{request_id}"' in stream
    assert '"terminal": true' in stream
    assert "event: done" not in stream


def test_draft_group_and_interject_stream_errors_are_terminal() -> None:
    character = CharacterCard(id="char-1", name="测试角色")
    group_chat = Chat(
        id="group-1",
        characterId=character.id,
        isGroup=True,
        memberIds=[character.id],
    )
    draft_chat = Chat(id="chat-1", characterId=character.id)
    settings = Settings()

    async def run() -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        cases = [
            (
                generate_draft_help,
                DraftHelpRequest(chatId=draft_chat.id, mode="write"),
                draft_chat,
                "/api/generate/draft-help",
                "req_draft_123",
            ),
            (
                generate_group_response,
                GroupGenerateRequest(chatId=group_chat.id, characterId=character.id),
                group_chat,
                "/api/generate/group",
                "req_group_123",
            ),
            (
                generate_single_interject,
                SingleInterjectRequest(chatId=group_chat.id, characterId=character.id),
                group_chat,
                "/api/generate/interject",
                "req_interject_123",
            ),
        ]
        for route, body, chat, path, request_id in cases:
            with ExitStack() as stack:
                _enter_common_generation_patches(
                    stack,
                    chat=chat,
                    character=character,
                    settings=settings,
                )
                stack.enter_context(
                    patch("app.routes.generate._resolve_char_name_for_draft_help", return_value="测试角色")
                )
                stack.enter_context(patch("app.routes.generate.stream_chat_completions", _failing_stream))
                response = await route(body, _request(path, request_id))
                results.append((await _consume_stream(response), request_id))
        return results

    for stream, request_id in asyncio.run(run()):
        _assert_terminal_error_stream(stream, request_id)


def test_draft_nonstream_failure_uses_error_envelope() -> None:
    character = CharacterCard(id="char-1", name="测试角色")
    chat = Chat(id="chat-1", characterId=character.id)
    settings = Settings(streamEnabled=False)
    upstream_request = httpx.Request(
        "POST",
        "https://provider.example/v1/chat/completions",
    )

    async def run():
        with ExitStack() as stack:
            _enter_common_generation_patches(
                stack,
                chat=chat,
                character=character,
                settings=settings,
            )
            stack.enter_context(
                patch("app.routes.generate._resolve_char_name_for_draft_help", return_value="测试角色")
            )
            stack.enter_context(
                patch(
                    "app.routes.generate.chat_completions_message",
                    side_effect=httpx.ReadTimeout("timed out", request=upstream_request),
                )
            )
            return await generate_draft_help(
                DraftHelpRequest(chatId=chat.id, mode="write"),
                _request("/api/generate/draft-help", "req_draft_rest_123"),
            )

    response = asyncio.run(run())
    body = json.loads(response.body)
    assert response.status_code == 504
    assert body["code"] == "upstream_timeout"
    assert body["requestId"] == "req_draft_rest_123"
    assert "ok" not in body


def test_group_and_interject_nonstream_failures_use_error_envelope() -> None:
    character = CharacterCard(id="char-1", name="测试角色")
    chat = Chat(
        id="group-1",
        characterId=character.id,
        isGroup=True,
        memberIds=[character.id],
    )
    settings = Settings(streamEnabled=False)

    async def run(route, body, path: str, request_id: str):
        upstream_request = httpx.Request(
            "POST",
            "https://provider.example/v1/chat/completions",
        )
        error = httpx.ReadTimeout("timed out", request=upstream_request)
        with ExitStack() as stack:
            _enter_common_generation_patches(
                stack,
                chat=chat,
                character=character,
                settings=settings,
            )
            stack.enter_context(
                patch("app.routes.generate.chat_completions", side_effect=error)
            )
            stack.enter_context(
                patch("app.routes.generate.chat_completions_message", side_effect=error)
            )
            return await route(body, _request(path, request_id))

    cases = [
        (
            generate_group_response,
            GroupGenerateRequest(chatId=chat.id, characterId=character.id),
            "/api/generate/group",
            "req_group_rest_123",
        ),
        (
            generate_single_interject,
            SingleInterjectRequest(chatId=chat.id, characterId=character.id),
            "/api/generate/interject",
            "req_interject_rest_123",
        ),
    ]
    for route, body, path, request_id in cases:
        response = asyncio.run(run(route, body, path, request_id))
        payload = json.loads(response.body)
        assert response.status_code == 504
        assert payload["code"] == "upstream_timeout"
        assert payload["requestId"] == request_id
        assert "ok" not in payload


def test_group_and_interject_web_search_missing_config_fast_fail() -> None:
    character = CharacterCard(id="char-1", name="测试角色")
    chat = Chat(
        id="group-1",
        characterId=character.id,
        isGroup=True,
        memberIds=[character.id],
    )
    settings = Settings()

    async def run(route, body, path: str) -> AppError:
        with (
            patch("app.routes.generate.load_chat", return_value=chat),
            patch("app.routes.generate.load_settings", return_value=settings),
            patch("app.routes.generate.ensure_mvu_worker"),
        ):
            try:
                await route(body, _request(path, "req_search_config"))
            except AppError as error:
                return error
        raise AssertionError("expected AppError")

    cases = [
        (
            generate_group_response,
            GroupGenerateRequest(
                chatId=chat.id,
                characterId=character.id,
                webSearchEnabled=True,
            ),
            "/api/generate/group",
        ),
        (
            generate_single_interject,
            SingleInterjectRequest(
                chatId=chat.id,
                characterId=character.id,
                webSearchEnabled=True,
            ),
            "/api/generate/interject",
        ),
    ]
    for route, body, path in cases:
        error = asyncio.run(run(route, body, path))
        assert error.code == "web_search_not_configured"
        assert error.status_code == 400
