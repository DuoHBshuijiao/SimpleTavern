"""知识图谱 MVU 工具 handlers。"""

from __future__ import annotations

from typing import Any

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R
from app.services import knowledge_graph as kg_svc
from app.services.knowledge_graph import KnowledgeGraphError


def _handle_kg_error(exc: KnowledgeGraphError) -> dict[str, Any]:
    code = R.NOT_FOUND if exc.status_code == 404 else R.VALIDATION_ERROR
    if exc.status_code == 403:
        code = R.FORBIDDEN
    if exc.status_code == 409:
        code = R.CONFLICT
    return R.err(code, str(exc))


def handle_kg_upsert_entity(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="kg_upsert_entity")
    name = str(args.get("name") or "").strip()
    entity_type = str(args.get("type") or "").strip()
    if not name:
        return R.err(R.VALIDATION_ERROR, "name is required", tool="kg_upsert_entity")
    if entity_type not in ("人物", "地点", "物品", "势力", "事件"):
        return R.err(R.VALIDATION_ERROR, "invalid type", tool="kg_upsert_entity")
    props_raw = args.get("properties")
    properties: dict[str, str] = {}
    if isinstance(props_raw, dict):
        properties = {str(k): str(v) for k, v in props_raw.items()}
    message_id = getattr(ctx, "trigger_message_id", None) or args.get("message_id")
    try:
        kg, entity_id = kg_svc.upsert_entity(
            chat_id,
            name=name,
            entity_type=entity_type,  # type: ignore[arg-type]
            properties=properties,
            source="mvu_agent",
            message_id=str(message_id) if message_id else None,
        )
    except KnowledgeGraphError as e:
        return _handle_kg_error(e)
    return R.ok({"entityId": entity_id, "version": kg.version}, tool="kg_upsert_entity")


def handle_kg_delete_entity(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="kg_delete_entity")
    entity_id = str(args.get("entity_id") or "").strip()
    if not entity_id:
        return R.err(R.VALIDATION_ERROR, "entity_id is required", tool="kg_delete_entity")
    try:
        kg = kg_svc.delete_entity(chat_id, entity_id, source="mvu_agent")
    except KnowledgeGraphError as e:
        return _handle_kg_error(e)
    return R.ok({"version": kg.version}, tool="kg_delete_entity")


def handle_kg_upsert_relation(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="kg_upsert_relation")
    subject_id = str(args.get("subject_id") or "").strip()
    predicate = str(args.get("predicate") or "").strip()
    object_id = str(args.get("object_id") or "").strip()
    if not subject_id or not predicate or not object_id:
        return R.err(
            R.VALIDATION_ERROR,
            "subject_id, predicate, object_id are required",
            tool="kg_upsert_relation",
        )
    confidence = args.get("confidence")
    try:
        conf = float(confidence) if confidence is not None else 1.0
    except (TypeError, ValueError):
        conf = 1.0
    conf = max(0.0, min(1.0, conf))
    message_id = getattr(ctx, "trigger_message_id", None) or args.get("message_id")
    try:
        kg = kg_svc.upsert_relation(
            chat_id,
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=conf,
            source="mvu_agent",
            message_id=str(message_id) if message_id else None,
        )
    except KnowledgeGraphError as e:
        return _handle_kg_error(e)
    return R.ok({"version": kg.version}, tool="kg_upsert_relation")


def handle_kg_get_context(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="kg_get_context")
    from app.storage import load_knowledge_graph

    kg = load_knowledge_graph(chat_id)
    if kg is None or not kg_svc.has_graph_data(kg):
        return R.ok({"contextText": "", "version": 0}, tool="kg_get_context")
    text = kg_svc.render_context_text(kg)
    return R.ok({"contextText": text, "version": kg.version}, tool="kg_get_context")


def handle_kg_query(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="kg_query")
    entity_name = args.get("entity_name")
    relation_type = args.get("relation_type")
    entity_type = args.get("type")
    et = str(entity_type).strip() if entity_type else None
    if et and et not in ("人物", "地点", "物品", "势力", "事件"):
        return R.err(R.VALIDATION_ERROR, "invalid type", tool="kg_query")
    try:
        data = kg_svc.query_graph(
            chat_id,
            entity_name=str(entity_name).strip() if entity_name else None,
            relation_type=str(relation_type).strip() if relation_type else None,
            entity_type=et,  # type: ignore[arg-type]
        )
    except KnowledgeGraphError as e:
        return _handle_kg_error(e)
    return R.ok(data, tool="kg_query")
