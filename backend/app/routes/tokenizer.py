"""
Tokenizer 路由模块

提供 token 数估算 API，用于长期记忆与对话长度展示。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.storage import load_chat
from app.tokenizer_service import count_tokens

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


@router.get("/tokenizer/chat-count")
def count_chat_tokens(chatId: str = Query(..., description="会话 ID")) -> dict:
    """
    计算指定会话 chat.json 中对话内容的 token 数。

    响应: { "tokens": number | null }，null 表示 tokenizer 不可用或会话不存在。
    """
    try:
        chat = load_chat(chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="会话不存在")
    parts = []
    for msg in getattr(chat, "messages", []) or []:
        role = getattr(msg, "role", "unknown")
        content = getattr(msg, "content", "") or ""
        parts.append(f"{role}: {content}")
    text = "\n".join(parts)
    n = count_tokens(text)
    return {"tokens": n}
