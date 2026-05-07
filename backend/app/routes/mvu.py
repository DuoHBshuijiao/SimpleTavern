"""MVU 助手路由模块

提供 MVU 工作日志 SSE 流与状态变量读写端点：
    - GET /api/mvu/{chat_id}/stream: SSE 工作日志流
    - GET /api/mvu/{chat_id}/state: 读取 stateVariables
    - PUT /api/mvu/{chat_id}/state: 更新 stateVariables（聊天助手）
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas import StateVariables
from app.services.mvu_daemon import ensure_mvu_worker, subscribe, unsubscribe
from app.storage import load_chat, load_mvu_logs, save_chat_state_variables

router = APIRouter(tags=["mvu"])


def _sse(event: str, data_obj: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


@router.get("/mvu/{chat_id}/stream")
async def stream_mvu_work_log(chat_id: str) -> StreamingResponse:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    ensure_mvu_worker(chat_id)

    queue = subscribe(chat_id)

    async def event_iter() -> AsyncIterator[str]:
        seen_log_ids: set[str] = set()
        try:
            # 先订阅再读取 catch-up，避免读取窗口内实时事件丢失。
            catch_up = load_mvu_logs(chat.characterId, chat_id)
            catch_up = catch_up[-50:] if len(catch_up) > 50 else catch_up
            for entry in catch_up:
                # 历史日志只用于面板补齐，不应驱动前端 MVU 运行态动画。
                eid = str(getattr(entry, "id", "") or "")
                if eid:
                    seen_log_ids.add(eid)
                yield _sse("log_history", entry.model_dump(mode="json"))

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    # 同连接内按 log_entry.id 去重，避免 catch-up 与实时重叠时重复。
                    if event.kind in ("log_entry", "log_history") and isinstance(event.data, dict):
                        eid = str(event.data.get("id") or "")
                        if eid and eid in seen_log_ids:
                            continue
                        if eid:
                            seen_log_ids.add(eid)
                    yield _sse(event.kind, event.data)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {"ts": ""})
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(chat_id, queue)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mvu/{chat_id}/state")
def get_mvu_state(chat_id: str):
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    state = chat.stateVariables
    return {
        "ok": True,
        "stateVariables": state.model_dump(mode="json") if state else None,
    }


@router.put("/mvu/{chat_id}/state")
def update_mvu_state(chat_id: str, body: StateVariables):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    body.source = "chat_assistant"
    updated = save_chat_state_variables(chat_id, body)
    return {
        "ok": True,
        "stateVariables": updated.stateVariables.model_dump(mode="json") if updated.stateVariables else None,
    }
