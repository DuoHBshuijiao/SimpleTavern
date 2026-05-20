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

from app.schemas import (
    KgEntityUpsertBody,
    KgRelationDeleteBody,
    KgRelationUpsertBody,
    StateVariables,
)
from app.services import knowledge_graph as kg_svc
from app.services.knowledge_graph import KnowledgeGraphError, kg_error_to_http
from app.services.mvu_daemon import ensure_mvu_worker, subscribe, unsubscribe
from app.storage import load_chat, load_knowledge_graph, load_mvu_logs, save_chat_state_variables

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


def _kg_response(kg):
    return {
        "ok": True,
        "knowledgeGraph": kg.model_dump(mode="json") if kg else None,
        "hasData": kg_svc.has_graph_data(kg),
    }


@router.get("/mvu/{chat_id}/knowledge-graph")
def get_knowledge_graph(chat_id: str):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    kg = load_knowledge_graph(chat_id)
    return _kg_response(kg)


@router.delete("/mvu/{chat_id}/knowledge-graph")
def clear_knowledge_graph(chat_id: str):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    try:
        kg_svc.clear_graph(chat_id)
    except KnowledgeGraphError as e:
        raise kg_error_to_http(e)
    return {"ok": True, "knowledgeGraph": None, "hasData": False}


@router.post("/mvu/{chat_id}/knowledge-graph/entities")
def upsert_knowledge_graph_entity(chat_id: str, body: KgEntityUpsertBody):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    try:
        kg, entity_id = kg_svc.upsert_entity(
            chat_id,
            name=body.name,
            entity_type=body.type,
            properties=body.properties,
            entity_id=body.entityId,
            source="user",
            expected_version=body.expectedVersion,
        )
    except KnowledgeGraphError as e:
        raise kg_error_to_http(e)
    resp = _kg_response(kg)
    resp["entityId"] = entity_id
    return resp


@router.delete("/mvu/{chat_id}/knowledge-graph/entities/{entity_id}")
def delete_knowledge_graph_entity(chat_id: str, entity_id: str, expectedVersion: int | None = None):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    try:
        kg = kg_svc.delete_entity(
            chat_id,
            entity_id,
            source="user",
            expected_version=expectedVersion,
        )
    except KnowledgeGraphError as e:
        raise kg_error_to_http(e)
    return _kg_response(kg)


@router.post("/mvu/{chat_id}/knowledge-graph/relations")
def upsert_knowledge_graph_relation(chat_id: str, body: KgRelationUpsertBody):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    try:
        kg = kg_svc.upsert_relation(
            chat_id,
            subject_id=body.subjectId,
            predicate=body.predicate,
            object_id=body.objectId,
            confidence=body.confidence,
            source="user",
            expected_version=body.expectedVersion,
        )
    except KnowledgeGraphError as e:
        raise kg_error_to_http(e)
    return _kg_response(kg)


@router.delete("/mvu/{chat_id}/knowledge-graph/relations")
def delete_knowledge_graph_relation(chat_id: str, body: KgRelationDeleteBody):
    try:
        load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    try:
        kg = kg_svc.delete_relation(
            chat_id,
            subject_id=body.subjectId,
            predicate=body.predicate,
            object_id=body.objectId,
            source="user",
            expected_version=body.expectedVersion,
        )
    except KnowledgeGraphError as e:
        raise kg_error_to_http(e)
    return _kg_response(kg)
