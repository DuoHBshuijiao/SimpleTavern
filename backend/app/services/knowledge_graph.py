"""知识图谱领域服务 — MVU 工具与 REST 共用。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.group_mvu import resolve_chat_mvu_runtime_enablement
from app.schemas import (
    KgEntity,
    KgEntityType,
    KgRelation,
    KgSource,
    KnowledgeGraph,
)
from app.storage import delete_knowledge_graph, load_chat, load_knowledge_graph, save_knowledge_graph


class KnowledgeGraphError(Exception):
    """业务错误，可映射为 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400, *, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code or "knowledge_graph_error"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _norm_name(name: str) -> str:
    return (name or "").strip().casefold()


def _active_entities(kg: KnowledgeGraph) -> list[KgEntity]:
    return [e for e in kg.entities if not e.deleted]


def _entity_by_id(kg: KnowledgeGraph, entity_id: str) -> KgEntity | None:
    for e in kg.entities:
        if e.id == entity_id and not e.deleted:
            return e
    return None


def _find_entity_by_name_type(kg: KnowledgeGraph, name: str, entity_type: KgEntityType) -> KgEntity | None:
    key = (_norm_name(name), entity_type)
    for e in kg.entities:
        if e.deleted:
            continue
        if (_norm_name(e.name), e.type) == key:
            return e
    return None


def has_graph_data(kg: KnowledgeGraph | None) -> bool:
    if kg is None:
        return False
    return len(_active_entities(kg)) > 0


def _require_mvu_enabled(chat_id: str):
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise KnowledgeGraphError("chat not found", 404, code="chat_not_found")
    enablement = resolve_chat_mvu_runtime_enablement(chat)
    if enablement.character_error is not None:
        err = enablement.character_error
        raise KnowledgeGraphError(
            err.message,
            err.status_code,
            code=err.code,
        )
    if not enablement.enabled:
        raise KnowledgeGraphError(
            "MVU runtime not enabled for this chat",
            403,
            code="mvu_runtime_disabled",
        )
    return chat


def _check_version(kg: KnowledgeGraph, expected: int | None) -> None:
    if expected is None:
        return
    if kg.version != expected:
        raise KnowledgeGraphError(
            f"version conflict: expected {expected}, got {kg.version}",
            409,
        )


def _bump_and_save(chat_id: str, kg: KnowledgeGraph, source: KgSource) -> KnowledgeGraph:
    kg.version = (kg.version or 0) + 1
    kg.source = source
    kg.updatedAt = _now_iso()
    return save_knowledge_graph(chat_id, kg)


def ensure_graph(chat_id: str, *, source: KgSource = "mvu_agent") -> KnowledgeGraph:
    _require_mvu_enabled(chat_id)
    kg = load_knowledge_graph(chat_id)
    if kg is not None:
        return kg
    empty = KnowledgeGraph(
        entities=[],
        relations=[],
        version=0,
        updatedAt=_now_iso(),
        source=source,
    )
    return save_knowledge_graph(chat_id, empty)


def upsert_entity(
    chat_id: str,
    *,
    name: str,
    entity_type: KgEntityType,
    properties: dict[str, str] | None = None,
    entity_id: str | None = None,
    source: KgSource = "mvu_agent",
    message_id: str | None = None,
    expected_version: int | None = None,
) -> tuple[KnowledgeGraph, str]:
    _require_mvu_enabled(chat_id)
    kg = ensure_graph(chat_id, source=source)
    _check_version(kg, expected_version)

    name = (name or "").strip()
    if not name:
        raise KnowledgeGraphError("name is required")

    props = dict(properties or {})
    entity: KgEntity | None = None

    if entity_id:
        for e in kg.entities:
            if e.id == entity_id:
                entity = e
                break
        if entity is None:
            raise KnowledgeGraphError(f"entity not found: {entity_id}", 404)
        entity.deleted = False
        entity.name = name
        entity.type = entity_type
        entity.properties = {**entity.properties, **props}
    else:
        entity = _find_entity_by_name_type(kg, name, entity_type)
        if entity is None:
            entity = KgEntity(
                id=uuid4().hex,
                name=name,
                type=entity_type,
                properties=props,
                firstMentionedAt=message_id,
                deleted=False,
            )
            kg.entities.append(entity)
        else:
            entity.properties = {**entity.properties, **props}
            if message_id and not entity.firstMentionedAt:
                entity.firstMentionedAt = message_id

    saved = _bump_and_save(chat_id, kg, source)
    return saved, entity.id


def delete_entity(
    chat_id: str,
    entity_id: str,
    *,
    source: KgSource = "mvu_agent",
    expected_version: int | None = None,
) -> KnowledgeGraph:
    _require_mvu_enabled(chat_id)
    kg = load_knowledge_graph(chat_id)
    if kg is None:
        raise KnowledgeGraphError("knowledge graph not found", 404)
    _check_version(kg, expected_version)

    found = False
    for e in kg.entities:
        if e.id == entity_id:
            e.deleted = True
            found = True
            break
    if not found:
        raise KnowledgeGraphError(f"entity not found: {entity_id}", 404)

    kg.relations = [
        r
        for r in kg.relations
        if r.subject != entity_id and r.object != entity_id
    ]
    return _bump_and_save(chat_id, kg, source)


def upsert_relation(
    chat_id: str,
    *,
    subject_id: str,
    predicate: str,
    object_id: str,
    confidence: float = 1.0,
    source: KgSource = "mvu_agent",
    message_id: str | None = None,
    expected_version: int | None = None,
) -> KnowledgeGraph:
    _require_mvu_enabled(chat_id)
    kg = ensure_graph(chat_id, source=source)
    _check_version(kg, expected_version)

    predicate = (predicate or "").strip()
    if not predicate:
        raise KnowledgeGraphError("predicate is required")

    if _entity_by_id(kg, subject_id) is None:
        raise KnowledgeGraphError(f"subject entity not found: {subject_id}", 404)

    # object：若匹配已有实体 id，则必须为未删除实体；否则视为字面量字符串
    if any(e.id == object_id for e in kg.entities):
        if _entity_by_id(kg, object_id) is None:
            raise KnowledgeGraphError(f"object entity not found or deleted: {object_id}", 404)

    existing: KgRelation | None = None
    for r in kg.relations:
        if r.subject == subject_id and r.predicate == predicate and r.object == object_id:
            existing = r
            break

    if existing is not None:
        existing.confidence = confidence
        if message_id and not existing.establishedAt:
            existing.establishedAt = message_id
    else:
        kg.relations.append(
            KgRelation(
                subject=subject_id,
                predicate=predicate,
                object=object_id,
                establishedAt=message_id,
                confidence=confidence,
            )
        )

    return _bump_and_save(chat_id, kg, source)


def delete_relation(
    chat_id: str,
    *,
    subject_id: str,
    predicate: str,
    object_id: str,
    source: KgSource = "user",
    expected_version: int | None = None,
) -> KnowledgeGraph:
    _require_mvu_enabled(chat_id)
    kg = load_knowledge_graph(chat_id)
    if kg is None:
        raise KnowledgeGraphError("knowledge graph not found", 404)
    _check_version(kg, expected_version)

    before = len(kg.relations)
    kg.relations = [
        r
        for r in kg.relations
        if not (r.subject == subject_id and r.predicate == predicate and r.object == object_id)
    ]
    if len(kg.relations) == before:
        raise KnowledgeGraphError("relation not found", 404)
    return _bump_and_save(chat_id, kg, source)


def query_graph(
    chat_id: str,
    *,
    entity_name: str | None = None,
    relation_type: str | None = None,
    entity_type: KgEntityType | None = None,
) -> dict[str, Any]:
    kg = load_knowledge_graph(chat_id)
    if kg is None:
        return {"entities": [], "relations": []}

    entities = _active_entities(kg)
    if entity_name:
        key = _norm_name(entity_name)
        entities = [e for e in entities if key in _norm_name(e.name)]
    if entity_type:
        entities = [e for e in entities if e.type == entity_type]

    entity_ids = {e.id for e in entities}
    relations = list(kg.relations)
    if relation_type:
        pred_key = relation_type.strip().casefold()
        relations = [r for r in relations if pred_key in r.predicate.casefold()]
    if entity_name or entity_type:
        relations = [
            r
            for r in relations
            if r.subject in entity_ids or r.object in entity_ids
        ]

    return {
        "entities": [e.model_dump(mode="json") for e in entities],
        "relations": [r.model_dump(mode="json") for r in relations],
    }


def _entity_display_props(e: KgEntity) -> str:
    if not e.properties:
        return ""
    parts = [f"{k}：{v}" for k, v in e.properties.items()]
    return "，".join(parts)


def _entity_label(e: KgEntity) -> str:
    props = _entity_display_props(e)
    line = f"- {e.name}"
    if props:
        line += f"：{props}"
    if e.firstMentionedAt:
        line += f"（首次提及于 {e.firstMentionedAt}）"
    return line


def _resolve_object_name(kg: KnowledgeGraph, object_ref: str) -> str:
    ent = _entity_by_id(kg, object_ref)
    if ent is not None:
        return ent.name
    for e in kg.entities:
        if e.id == object_ref and not e.deleted:
            return e.name
    return object_ref


def render_context_text(kg: KnowledgeGraph) -> str:
    """生成注入 RP prompt 的 KnowledgeGraph 标签内文。"""
    entities = _active_entities(kg)
    if not entities:
        return ""

    type_order: list[KgEntityType] = ["人物", "地点", "物品", "势力", "事件"]
    sections: list[str] = []

    for t in type_order:
        group = [e for e in entities if e.type == t]
        if not group:
            continue
        lines = [_entity_label(e) for e in group]
        sections.append(f"[{t}]\n" + "\n".join(lines))

    if kg.relations:
        rel_lines: list[str] = []
        for r in kg.relations:
            subj = _entity_by_id(kg, r.subject)
            subj_name = subj.name if subj else r.subject
            obj_name = _resolve_object_name(kg, r.object)
            conf = r.confidence
            if conf < 1.0:
                rel_lines.append(f"- {subj_name} {r.predicate} {obj_name}（置信度: {conf}）")
            else:
                rel_lines.append(f"- {subj_name} {r.predicate} {obj_name}")
        sections.append("[关系]\n" + "\n".join(rel_lines))

    return "\n\n".join(sections)


def clear_graph(chat_id: str) -> None:
    _require_mvu_enabled(chat_id)
    delete_knowledge_graph(chat_id)


def kg_error_to_http(exc: KnowledgeGraphError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
        },
    )
