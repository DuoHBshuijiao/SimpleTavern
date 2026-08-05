"""
共享出站 HTTP client（T-803-3A）

进程级复用 httpx AsyncClient / Client，避免每次 LLM/搜索请求新建连接池。
请求级 timeout 仍可由调用方覆盖，不改变业务超时语义。
"""

from __future__ import annotations

import threading
from typing import Any

import httpx

# 默认超时偏保守；流式 LLM 用 timeout=None 覆盖。
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)

_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None
_async_lock = threading.Lock()
_sync_lock = threading.Lock()


def _build_async_client(**kwargs: Any) -> httpx.AsyncClient:
    opts: dict[str, Any] = {
        "timeout": DEFAULT_TIMEOUT,
        "limits": DEFAULT_LIMITS,
        "follow_redirects": False,
    }
    opts.update(kwargs)
    return httpx.AsyncClient(**opts)


def _build_sync_client(**kwargs: Any) -> httpx.Client:
    opts: dict[str, Any] = {
        "timeout": DEFAULT_TIMEOUT,
        "limits": DEFAULT_LIMITS,
        "follow_redirects": False,
    }
    opts.update(kwargs)
    return httpx.Client(**opts)


def _is_closed(client: object | None) -> bool:
    if client is None:
        return True
    return bool(getattr(client, "is_closed", False))


def get_async_http_client() -> httpx.AsyncClient:
    """返回进程级 AsyncClient；测试/未 lifespan 时懒创建。"""
    global _async_client
    if _async_client is not None and not _is_closed(_async_client):
        return _async_client
    with _async_lock:
        if _async_client is None or _is_closed(_async_client):
            _async_client = _build_async_client()
        return _async_client


def get_sync_http_client() -> httpx.Client:
    """返回进程级同步 Client；供 assistant tool 等同步路径。"""
    global _sync_client
    if _sync_client is not None and not _is_closed(_sync_client):
        return _sync_client
    with _sync_lock:
        if _sync_client is None or _is_closed(_sync_client):
            _sync_client = _build_sync_client()
        return _sync_client


async def startup_http_clients() -> None:
    """应用启动时预创建共享 client。"""
    get_async_http_client()
    get_sync_http_client()


async def shutdown_http_clients() -> None:
    """应用关闭时释放连接池。"""
    global _async_client, _sync_client
    async_client = _async_client
    sync_client = _sync_client
    _async_client = None
    _sync_client = None
    if async_client is not None and not _is_closed(async_client):
        await async_client.aclose()  # type: ignore[union-attr]
    if sync_client is not None and not _is_closed(sync_client):
        sync_client.close()  # type: ignore[union-attr]


def reset_http_clients_for_tests() -> None:
    """测试辅助：强制丢弃当前 client（不保证已 aclose）。"""
    global _async_client, _sync_client
    _async_client = None
    _sync_client = None
