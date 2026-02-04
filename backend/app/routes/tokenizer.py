"""
Tokenizer 路由模块

提供 token 数估算 API，用于长期记忆与对话长度展示。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.storage import load_chat
from app.tokenizer_service import count_tokens, count_tokens_for_messages

router = APIRouter(tags=["tokenizer"])


class CountTextRequest(BaseModel):
    text: str | None = None


@router.post("/tokenizer/count")
def count_text_tokens(body: CountTextRequest) -> dict:
    """
    计算给定文本的 token 数（用于长期记忆等）。

    请求体: { "text": "..." }
    响应: { "tokens": number | null }，null 表示 tokenizer 不可用。
    """
    text = body.text if body.text is not None else ""
    n = count_tokens(text)
    return {"tokens": n}


def _message_has_memory_updated_after(msg) -> bool:
    if getattr(msg, "memoryUpdatedAfterThis", False):
        return True
    extra = getattr(msg, "model_extra", None)
    return bool(extra and extra.get("memoryUpdatedAfterThis"))


def _message_to_count_dict(msg) -> dict:
    role = getattr(msg, "role", "unknown")
    content = (getattr(msg, "content", None) or "") or ""
    out = {"role": role, "content": content}
    extra = getattr(msg, "model_extra", None)
    if isinstance(extra, dict) and "reasoning_content" in extra:
        out["reasoning_content"] = extra["reasoning_content"]
    return out


@router.get("/tokenizer/chat-count")
def count_chat_tokens(chatId: str = Query(..., description="会话 ID")) -> dict:
    """
    计算指定会话 chat.json 中对话内容的 token 数，以及自上次保存记忆以来的消息条数与 token 数。

    响应: { "tokens": number | null, "messagesSinceLastMemoryUpdate": number | null, "tokensSinceLastMemoryUpdate": number | null }
    """
    try:
        chat = load_chat(chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = getattr(chat, "messages", []) or []
    parts = []
    for msg in messages:
        role = getattr(msg, "role", "unknown")
        content = getattr(msg, "content", "") or ""
        parts.append(f"{role}: {content}")
    text = "\n".join(parts)
    n = count_tokens(text)

    last_mark_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if _message_has_memory_updated_after(messages[i]):
            last_mark_index = i
            break
    messages_since: int | None = None
    tokens_since: int | None = None
    if last_mark_index >= 0:
        messages_since = len(messages) - last_mark_index - 1
        tail = [_message_to_count_dict(m) for m in messages[last_mark_index + 1 :]]
        tokens_since = count_tokens_for_messages(tail) if tail else 0

    return {
        "tokens": n,
        "messagesSinceLastMemoryUpdate": messages_since,
        "tokensSinceLastMemoryUpdate": tokens_since,
    }
