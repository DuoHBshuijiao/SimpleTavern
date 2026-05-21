"""Knowledge graph RP prompt injection helpers."""

from __future__ import annotations

from typing import Any

from app.schemas import KnowledgeGraphBeforeLastRole, KnowledgeGraphInjectPosition

_KG_TOOL_NAMES = frozenset({
    "kg_upsert_entity",
    "kg_delete_entity",
    "kg_upsert_relation",
    "kg_get_context",
    "kg_query",
})


def is_knowledge_graph_enabled(chat: Any) -> bool:
    """会话级知识图谱是否启用（None 视为 True）。"""
    ov = getattr(chat, "overrides", None)
    if ov is None:
        return True
    val = getattr(ov, "knowledgeGraphEnabled", None)
    return val is not False


def resolve_inject_position(chat: Any) -> KnowledgeGraphInjectPosition:
    ov = getattr(chat, "overrides", None)
    if ov is None:
        return "legacy"
    pos = getattr(ov, "knowledgeGraphInjectPosition", None)
    if pos in ("before_system", "after_system", "depth", "before_last", "legacy"):
        return pos
    return "legacy"


def resolve_inject_depth(chat: Any) -> int:
    ov = getattr(chat, "overrides", None)
    if ov is None:
        return 5
    try:
        return max(0, int(getattr(ov, "knowledgeGraphInjectDepth", 5) or 5))
    except (TypeError, ValueError):
        return 5


def resolve_before_last_role(chat: Any) -> KnowledgeGraphBeforeLastRole:
    ov = getattr(chat, "overrides", None)
    if ov is None:
        return "assistant"
    role = getattr(ov, "knowledgeGraphBeforeLastRole", None)
    if role in ("assistant", "system", "user"):
        return role
    return "assistant"


def format_knowledge_graph_block(body: str) -> str:
    return f"\n\n<KnowledgeGraph>\n{body.strip()}\n</KnowledgeGraph>"


def _first_system_index(messages: list[dict]) -> int | None:
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            return i
    return None


def _leading_system_end(messages: list[dict]) -> int:
    """连续首部 system 块之后的起始索引。"""
    i = 0
    while i < len(messages) and messages[i].get("role") == "system":
        i += 1
    return i


def _append_to_message_content(msg: dict, block: str) -> bool:
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    msg["content"] = f"{content.rstrip()}{block}"
    return True


def _prepend_to_message_content(msg: dict, block: str) -> bool:
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    msg["content"] = f"{block.lstrip()}{content}"
    return True


def _insert_system_message(messages: list[dict], index: int, block: str) -> None:
    messages.insert(index, {"role": "system", "content": block.strip()})


def apply_knowledge_graph_injection(
    messages: list[dict],
    chat: Any,
    body: str,
) -> bool:
    """按会话配置将知识图谱块注入 messages（原地修改）。成功返回 True。"""
    if not body.strip():
        return False

    block = format_knowledge_graph_block(body)
    position = resolve_inject_position(chat)

    if position == "legacy":
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            if _append_to_message_content(msg, block):
                return True
        return False

    if position == "before_system":
        idx = _first_system_index(messages)
        if idx is not None:
            return _prepend_to_message_content(messages[idx], block)
        _insert_system_message(messages, 0, block)
        return True

    if position == "after_system":
        idx = _first_system_index(messages)
        if idx is not None:
            return _append_to_message_content(messages[idx], block)
        _insert_system_message(messages, 0, block)
        return True

    if position == "depth":
        start = _leading_system_end(messages)
        tail = messages[start:]
        depth = resolve_inject_depth(chat)
        insert_at = start + max(0, len(tail) - depth)
        _insert_system_message(messages, insert_at, block)
        return True

    if position == "before_last":
        role = resolve_before_last_role(chat)
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == role:
                _insert_system_message(messages, i, block)
                return True
        return False

    return False


_MVU_BASE_TOOL_NAMES = frozenset({
    "mvu_get_session_state",
    "mvu_define_table",
    "mvu_set_cell",
    "mvu_get_chat_context",
    "read_mvu_logs",
    "chat_content_regex_manage",
    "character_content_regex_manage",
})


def mvu_tool_names(include_knowledge_graph: bool) -> frozenset[str]:
    names = set(_MVU_BASE_TOOL_NAMES)
    if include_knowledge_graph:
        names |= _KG_TOOL_NAMES
    return frozenset(names)
