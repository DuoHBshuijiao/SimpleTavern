"""Small JSON HTTP helper for OAuth (T-830)."""

from __future__ import annotations

from typing import Any

from app.services.http_client import get_async_http_client


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json_body: Any = None,
    timeout: float = 20.0,
) -> tuple[int, Any, str]:
    client = get_async_http_client()
    response = await client.request(
        method,
        url,
        headers=headers,
        data=data,
        json=json_body,
        timeout=timeout,
    )
    text = response.text
    parsed: Any = None
    if text:
        try:
            parsed = response.json()
        except Exception:  # noqa: BLE001 - 上游可能返回 HTML / 表单
            parsed = None
    return response.status_code, parsed, text
