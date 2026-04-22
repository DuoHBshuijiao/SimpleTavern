"""
与聊天导出 JSONL（simpletavern_chat_jsonl）同源的「精简正文」构建逻辑。

供 HTTP 导出与助手工具 chat_read_conversation（transcript 模式）复用，避免双份规则漂移。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.schemas import Chat, ChatMessage, Settings
from app.storage import load_character

_DATA_IMAGE_B64_RE = re.compile(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+")


def resolve_message_sender_name(m: ChatMessage, settings: Settings) -> str:
    """与导出 JSONL 一致：解析消息发言人的人类可读名称。"""
    if m.role == "assistant":
        if m.characterId:
            try:
                return load_character(m.characterId).name or ""
            except FileNotFoundError:
                pass
        return m.senderName or ""
    if m.role == "user":
        if m.senderPersonaId:
            persona = next((p for p in (settings.userPersonas or []) if p.id == m.senderPersonaId), None)
            if persona:
                return persona.name or ""
        if m.senderName:
            return m.senderName
        if settings.selectedPersonaId:
            persona = next((p for p in (settings.userPersonas or []) if p.id == settings.selectedPersonaId), None)
            if persona:
                return persona.name or ""
        return ""
    return ""


def build_jsonl_header_dict(chat: Chat) -> dict[str, Any]:
    """JSONL 首行：会话元数据（与导出文件第一行字段一致，ts 为构建时刻）。"""
    member_ids = chat.memberIds if chat.isGroup else [chat.characterId]
    participants: list[str] = []
    for mid in member_ids:
        try:
            participants.append(load_character(mid).name or mid)
        except FileNotFoundError:
            participants.append(mid)

    return {
        "type": "simpletavern_chat_jsonl",
        "version": 1,
        "chatId": chat.id,
        "title": chat.title,
        "isGroup": chat.isGroup,
        "participants": participants,
        "ts": datetime.now().astimezone().isoformat(),
    }


def build_transcript_rows_from_messages(messages: list[ChatMessage], settings: Settings) -> list[dict[str, str]]:
    """
    将消息序列转为与 JSONL 第 2 行起相同语义的行列表（每行 role/name/content）。
    跳过 tool 与 toolTrace；内联图替换为 [image]。
    """
    rows: list[dict[str, str]] = []
    for m in messages:
        if m.role == "tool":
            continue
        extra = m.model_dump(mode="json")
        if extra.get("toolTrace"):
            continue
        name = resolve_message_sender_name(m, settings)
        content = _DATA_IMAGE_B64_RE.sub("[image]", m.content or "")
        rows.append({"role": m.role, "name": name, "content": content})
    return rows


def slice_messages_since_memory_marker(messages: list[ChatMessage]) -> list[ChatMessage]:
    """从带 memoryUpdatedAfterThis 的消息起截取（含该条），与旧版 chat_read_conversation 行为一致。"""
    start = 0
    for i, m in enumerate(messages):
        d = m.model_dump(mode="json")
        if d.get("memoryUpdatedAfterThis") is True:
            start = i
            break
    return messages[start:]


def format_chat_as_jsonl_string(chat: Chat, settings: Settings) -> str:
    """供 HTTP 导出：完整 NDJSON 文本（头行 + 消息行）。"""
    lines: list[str] = [json.dumps(build_jsonl_header_dict(chat), ensure_ascii=False)]
    for row in build_transcript_rows_from_messages(chat.messages, settings):
        lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + "\n"
