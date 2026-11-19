from __future__ import annotations

import asyncio
from typing import Coroutine, TypeVar

from fastapi import Request


T = TypeVar("T")


class ClientDisconnected(Exception):
    pass


async def _wait_for_disconnect(request: Request) -> None:
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def until_client_disconnect(request: Request, operation: Coroutine[object, object, T]) -> T:
    task = asyncio.create_task(operation)
    disconnect = asyncio.create_task(_wait_for_disconnect(request))
    try:
        done, _ = await asyncio.wait({task, disconnect}, return_when=asyncio.FIRST_COMPLETED)
        if disconnect in done:
            raise ClientDisconnected
        return task.result()
    finally:
        task.cancel()
        disconnect.cancel()
        await asyncio.gather(task, disconnect, return_exceptions=True)
