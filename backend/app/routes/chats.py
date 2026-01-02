from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas import AppendMessageRequest, Chat, ChatMessage, CreateChatRequest, UpdateChatRequest, UpdateMessageRequest
from app.storage import delete_chat, list_chats, load_character, load_chat, load_settings, save_chat

router = APIRouter(tags=["chats"])


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def _merge_overrides(existing: Chat, incoming: UpdateChatRequest) -> None:
    if incoming.overrides is None:
        return
    ov = incoming.overrides
    if ov.prompt is not None:
        existing.overrides.prompt = ov.prompt

    # params 做“只覆盖非 None 字段”的合并，避免一次更新把旧参数清空
    for key in ("model", "temperature", "top_p", "max_tokens"):
        val = getattr(ov.params, key, None)
        if val is not None:
            setattr(existing.overrides.params, key, val)


@router.get("/chats", response_model=list[Chat])
def get_chats(characterId: str = Query(...)) -> list[Chat]:
    return list_chats(characterId)


def _replace_user_placeholder(text: str, user_name: str) -> str:
    """替换文本中的 {{user}} 占位符为用户名"""
    if not user_name:
        return text
    return text.replace("{{user}}", user_name)


@router.post("/chats", response_model=Chat)
def create_chat(req: CreateChatRequest) -> Chat:
    chat = Chat(characterId=req.characterId, title=req.title or "新对话")
    chat.createdAt = _now_iso()
    chat.updatedAt = _now_iso()
    
    # 获取用户Persona名称用于替换 {{user}}
    user_name = ""
    try:
        settings = load_settings()
        if settings.selectedPersonaId and settings.userPersonas:
            selected_persona = next((p for p in settings.userPersonas if p.id == settings.selectedPersonaId), None)
            if selected_persona:
                user_name = selected_persona.name
    except Exception:
        pass
    
    # 如果角色有首句，自动添加为 assistant 的第一条消息
    try:
        character = load_character(req.characterId)
        if character.firstMessage and character.firstMessage.strip():
            first_msg = character.firstMessage.strip()
            # 替换 {{user}} 为用户Persona名称
            if user_name:
                first_msg = _replace_user_placeholder(first_msg, user_name)
            chat.messages.append(ChatMessage(
                role="assistant",
                content=first_msg
            ))
    except FileNotFoundError:
        # 角色不存在时忽略，不影响会话创建
        pass
    
    return save_chat(chat)


@router.get("/chats/{chat_id}", response_model=Chat)
def get_chat(chat_id: str) -> Chat:
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")


@router.put("/chats/{chat_id}", response_model=Chat)
def update_chat(chat_id: str, req: UpdateChatRequest) -> Chat:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    if req.title is not None:
        chat.title = req.title
    _merge_overrides(chat, req)
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.post("/chats/{chat_id}/messages", response_model=Chat)
def append_message(chat_id: str, req: AppendMessageRequest) -> Chat:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    chat.messages.append(ChatMessage(role=req.role, content=req.content))
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.put("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def update_message(chat_id: str, message_id: str, req: UpdateMessageRequest) -> Chat:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    for m in chat.messages:
        if m.id == message_id:
            m.role = req.role
            m.content = req.content
            chat.updatedAt = _now_iso()
            return save_chat(chat)

    raise HTTPException(status_code=404, detail="message not found")


@router.delete("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def delete_message(chat_id: str, message_id: str) -> Chat:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    before = len(chat.messages)
    chat.messages = [m for m in chat.messages if m.id != message_id]
    if len(chat.messages) == before:
        raise HTTPException(status_code=404, detail="message not found")

    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: str) -> dict:
    delete_chat(chat_id)
    return {"ok": True}


