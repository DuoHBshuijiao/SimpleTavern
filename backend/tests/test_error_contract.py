from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import AppError, as_app_error, install_error_handlers, redact_sensitive_text
from app.request_context import RequestIdMiddleware
from app.routes.generate import _ensure_web_search_ready, generate_stream
from app.routes.llm import router as llm_router
from app.schemas import CharacterCard, Chat, GenerateStreamRequest, Settings
from app.services.http_log import log_outbound, redact_headers
from app.sse import sse_meta, sse_terminal_error


class _Payload(BaseModel):
    count: int


def _contract_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)

    @app.get("/app-error")
    async def app_error() -> None:
        raise AppError(
            code="example_failed",
            message="示例失败",
            source="test",
            status_code=409,
            suggested_action="修改输入",
        )

    @app.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("Authorization: Bearer sk-secret-should-not-leak")

    @app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(
            status_code=404,
            detail={"code": "chat_not_found", "message": "会话不存在"},
        )

    @app.post("/validation")
    async def validation(payload: _Payload) -> dict[str, int]:
        return payload.model_dump()

    return app


def test_app_error_returns_envelope_and_request_id() -> None:
    with TestClient(_contract_app(), raise_server_exceptions=False) as client:
        response = client.get("/app-error", headers={"X-Request-Id": "client_req_123"})

    assert response.status_code == 409
    assert response.headers["x-request-id"] == "client_req_123"
    assert response.json() == {
        "code": "example_failed",
        "message": "示例失败",
        "source": "test",
        "retryable": False,
        "requestId": "client_req_123",
        "suggestedAction": "修改输入",
    }


def test_unhandled_error_is_generic_and_does_not_leak_secret() -> None:
    with TestClient(_contract_app(), raise_server_exceptions=False) as client:
        response = client.get("/unexpected")

    body = response.json()
    assert response.status_code == 500
    assert body["code"] == "internal_error"
    assert body["requestId"] == response.headers["x-request-id"]
    assert "sk-secret" not in json.dumps(body)


def test_http_exception_and_validation_use_same_envelope() -> None:
    with TestClient(_contract_app(), raise_server_exceptions=False) as client:
        missing = client.get("/http-error")
        invalid = client.post("/validation", json={"count": "not-an-int"})

    assert missing.status_code == 404
    assert missing.json()["code"] == "chat_not_found"
    assert missing.json()["message"] == "会话不存在"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request_validation_failed"
    assert invalid.json()["requestId"] == invalid.headers["x-request-id"]


def test_upstream_status_and_timeout_mapping() -> None:
    request = httpx.Request("GET", "https://provider.example/v1/models")
    unauthorized = httpx.Response(
        401,
        request=request,
        json={"error": {"message": "invalid key"}},
    )
    rate_limited = httpx.Response(429, request=request, json={"error": "quota"})

    auth_error = as_app_error(
        httpx.HTTPStatusError("401", request=request, response=unauthorized),
        source="test.provider",
    )
    quota_error = as_app_error(
        httpx.HTTPStatusError("429", request=request, response=rate_limited),
        source="test.provider",
    )
    timeout_error = as_app_error(
        httpx.ReadTimeout("timed out", request=request),
        source="test.provider",
    )

    assert (auth_error.code, auth_error.status_code, auth_error.retryable) == (
        "provider_auth_failed",
        401,
        False,
    )
    assert (quota_error.code, quota_error.status_code, quota_error.retryable) == (
        "provider_quota_exceeded",
        429,
        True,
    )
    assert (timeout_error.code, timeout_error.status_code, timeout_error.retryable) == (
        "upstream_timeout",
        504,
        True,
    )


def test_sse_error_is_terminal_and_meta_contains_request_id() -> None:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    error_event = sse_terminal_error(
        httpx.ReadTimeout("timed out", request=request),
        request_id="req_sse_123",
        source="generate.stream",
    )
    meta_event = sse_meta(
        request_id="req_sse_123",
        provider="openai_compatible",
        protocol="openai_compatible_chat",
        resolved_model="test-model",
    )

    error_payload = json.loads(error_event.split("data: ", 1)[1])
    meta_payload = json.loads(meta_event.split("data: ", 1)[1])
    assert error_event.startswith("event: error\n")
    assert error_payload["terminal"] is True
    assert error_payload["code"] == "upstream_timeout"
    assert error_payload["requestId"] == "req_sse_123"
    assert "event: done" not in error_event
    assert meta_payload["requestId"] == "req_sse_123"
    assert meta_payload["resolvedModel"] == "test-model"


def test_llm_test_models_failure_is_not_empty_success() -> None:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(llm_router, prefix="/api")

    async def fail_models(_base_url: str, _api_key: str) -> list[str]:
        raise AppError(
            code="provider_auth_failed",
            message="上游服务鉴权失败",
            source="llm.test",
            status_code=401,
        )

    with patch("app.routes.llm.list_models_openai_compat", side_effect=fail_models):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/llm/test-models",
                json={"baseUrl": "https://provider.example/v1", "apiKey": "bad-key"},
            )

    assert response.status_code == 401
    assert response.json()["code"] == "provider_auth_failed"
    assert response.json() != []


def test_llm_models_empty_result_does_not_fallback_to_local_candidates() -> None:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(llm_router, prefix="/api")
    settings = Settings()
    settings.llm.modelCandidates = ["local-candidate"]
    settings.llm.defaultModel = "local-default"

    async def empty_models(_base_url: str, _api_key: str) -> list[str]:
        return []

    with (
        patch("app.routes.llm.load_settings", return_value=settings),
        patch("app.routes.llm.list_models_openai_compat", side_effect=empty_models),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/llm/models")

    assert response.status_code == 502
    assert response.json()["code"] == "model_list_empty"
    assert "local-candidate" not in response.text
    assert "local-default" not in response.text


def test_llm_test_models_empty_result_is_not_success() -> None:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(llm_router, prefix="/api")

    async def empty_models(_base_url: str, _api_key: str) -> list[str]:
        return []

    with patch("app.routes.llm.list_models_openai_compat", side_effect=empty_models):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/llm/test-models",
                json={"baseUrl": "https://provider.example/v1", "apiKey": "test-key"},
            )

    assert response.status_code == 502
    assert response.json()["code"] == "model_list_empty"
    assert response.json() != []


def test_web_search_requested_without_configuration_fast_fails() -> None:
    try:
        _ensure_web_search_ready(Settings(), requested=True)
    except AppError as error:
        assert error.code == "web_search_not_configured"
        assert error.status_code == 400
    else:
        raise AssertionError("expected AppError")


def test_http_log_carries_request_id_and_redacts_cookie() -> None:
    assert redact_headers({"Cookie": "session=secret", "Authorization": "Bearer secret"}) == {
        "Cookie": "***",
        "Authorization": "***",
    }

    async def run() -> dict:
        write_record = AsyncMock()
        with patch("app.services.http_log._write_record", write_record):
            async with log_outbound(
                source="llm",
                method="GET",
                url="https://provider.example/v1/models",
                request_id="req_log_123",
                request_headers={"Cookie": "session=secret"},
            ):
                pass
        return write_record.await_args.args[0]

    record = asyncio.run(run())
    assert record["requestId"] == "req_log_123"
    assert record["requestHeaders"]["Cookie"] == "***"


def test_http_log_uses_middleware_request_context() -> None:
    records: list[dict] = []
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)

    @app.get("/outbound-log")
    async def outbound_log() -> dict[str, bool]:
        async with log_outbound(
            source="llm",
            method="GET",
            url="https://provider.example/v1/models",
        ):
            pass
        return {"ok": True}

    async def capture(record: dict) -> None:
        records.append(record)

    with patch("app.services.http_log._write_record", side_effect=capture):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/outbound-log",
                headers={"X-Request-Id": "req_context_123"},
            )

    assert response.status_code == 200
    assert records[0]["requestId"] == "req_context_123"


def test_generate_stream_upstream_failure_emits_meta_then_error_without_done() -> None:
    chat = Chat(id="chat-1", characterId="char-1")
    character = CharacterCard(id="char-1", name="测试角色")
    settings = Settings()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/generate/stream",
            "headers": [],
            "query_string": b"",
            "state": {"request_id": "req_generate_123"},
        }
    )
    body = GenerateStreamRequest(
        chatId=chat.id,
        userMessage="hello",
        appendUserMessage=False,
    )

    async def fail_stream(**_kwargs):
        upstream_request = httpx.Request(
            "POST",
            "https://provider.example/v1/chat/completions",
        )
        raise httpx.ReadTimeout("timed out", request=upstream_request)
        yield  # pragma: no cover

    async def run() -> str:
        with (
            patch("app.routes.generate.load_chat", return_value=chat),
            patch("app.routes.generate.load_character", return_value=character),
            patch("app.routes.generate.load_settings", return_value=settings),
            patch("app.routes.generate.ensure_mvu_worker"),
            patch("app.routes.generate.collect_active_worldbooks", return_value=[]),
            patch(
                "app.routes.generate._resolve_generation_credentials",
                return_value=("https://provider.example/v1", "test-key"),
            ),
            patch("app.routes.generate.stream_chat_completions", fail_stream),
        ):
            response = await generate_stream(body, request)
            chunks: list[str] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
            return "".join(chunks)

    stream = asyncio.run(run())
    assert stream.index("event: meta") < stream.index("event: error")
    assert '"requestId": "req_generate_123"' in stream
    assert '"terminal": true' in stream
    assert "event: done" not in stream


def test_sensitive_text_redaction() -> None:
    redacted = redact_sensitive_text(
        'Authorization: Bearer sk-secret-123456 api_key="another-secret" cookie=session-secret'
    )
    assert "sk-secret" not in redacted
    assert "another-secret" not in redacted
    assert "session-secret" not in redacted
