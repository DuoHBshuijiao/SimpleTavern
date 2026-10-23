"""Small JSON HTTP helper for OAuth (T-830)."""

from __future__ import annotations

from typing import Any

import httpx


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json_body: Any = None,
    timeout: float = 20.0,
) -> tuple[int, Any, str]:
    # Credential resolution can run refresh in a short-lived worker event loop.
    # A process-wide AsyncClient would reuse connections bound to a closed loop.
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, data=data, json=json_body)
    text = response.text
    parsed: Any = None
    if text:
        try:
            parsed = response.json()
        except Exception:  # noqa: BLE001 - 上游可能返回 HTML / 表单
            parsed = None
    return response.status_code, parsed, text
