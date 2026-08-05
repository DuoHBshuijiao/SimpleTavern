"""T-803-3A: shared HTTP client reuse and lifecycle."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import http_client as hc


@pytest.fixture(autouse=True)
def _reset_clients():
    asyncio.run(hc.shutdown_http_clients())
    hc.reset_http_clients_for_tests()
    yield
    asyncio.run(hc.shutdown_http_clients())
    hc.reset_http_clients_for_tests()


def test_async_client_is_reused() -> None:
    a = hc.get_async_http_client()
    b = hc.get_async_http_client()
    assert a is b
    assert not a.is_closed


def test_sync_client_is_reused() -> None:
    a = hc.get_sync_http_client()
    b = hc.get_sync_http_client()
    assert a is b
    assert not a.is_closed


def test_shutdown_closes_and_get_recreates() -> None:
    first = hc.get_async_http_client()
    asyncio.run(hc.shutdown_http_clients())
    assert first.is_closed
    second = hc.get_async_http_client()
    assert second is not first
    assert not second.is_closed


def test_shared_clients_use_default_timeout() -> None:
    client = hc.get_async_http_client()
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect == hc.DEFAULT_TIMEOUT.connect
