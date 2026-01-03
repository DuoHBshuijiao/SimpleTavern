from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas import AppendMessageRequest, Chat, ChatMessage, CreateChatRequest, UpdateChatRequest, UpdateMessageRequest
from app.storage import delete_chat, list_chats, list_group_chats, load_character, load_chat, load_settings, save_chat

router = APIRouter(tags=["chats"])


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def _merge_overrides(existing: Chat, incoming: UpdateChatRequest) -> None:
    if incoming.overrides is None:
        return
    ov = incoming.overrides
    if ov.prompt is not None:
        existing.overrides.prompt = ov.prompt
    if getattr(ov, "pureAiMode", None) is not None:
        existing.overrides.pureAiMode = ov.pureAiMode

    # params 做“只覆盖非 None 字段”的合并，避免一次更新把旧参数清空
    for key in ("model", "temperature", "top_p", "max_tokens"):
        val = getattr(ov.params, key, None)
        if val is not None:
            setattr(existing.overrides.params, key, val)


@router.get("/chats", response_model=list[Chat])
def get_chats(characterId: str = Query(...)) -> list[Chat]:
    return list_chats(characterId)


@router.get("/chats/groups", response_model=list[Chat])
def get_group_chats() -> list[Chat]:
    """获取所有群聊"""
    return list_group_chats()


def _replace_user_placeholder(text: str, user_name: str) -> str:
    """替换文本中的 {{user}} 占位符为用户名"""
    if not user_name:
        return text
    return text.replace("{{user}}", user_name)


@router.post("/chats", response_model=Chat)
def create_chat(req: CreateChatRequest) -> Chat:
    # 判断是否为群聊
    is_group = req.isGroup
    
    if is_group:
        # 群聊：默认标题为"新群聊"，memberIds 必须有至少2个成员
        title = req.title or "新群聊"
        member_ids = req.memberIds or []
        # 确保 characterId（主角色）也在成员列表中
        if req.characterId and req.characterId not in member_ids:
            member_ids = [req.characterId] + member_ids
        chat = Chat(
            characterId=req.characterId,
            title=title,
            isGroup=True,
            memberIds=member_ids
        )
    else:
        # 单聊：保持原有逻辑
        chat = Chat(characterId=req.characterId, title=req.title or "新对话")
    
    # 写入会话级 pureAiMode（None 表示使用全局）
    chat.overrides.pureAiMode = req.pureAiMode
    
    # 群聊创建时可写入 memberSettings
    if is_group and req.memberSettings:
        for member_id, s in req.memberSettings.items():
            chat.memberSettings[member_id] = s
    
    chat.createdAt = _now_iso()
    chat.updatedAt = _now_iso()
    
    # 获取用户Persona名称用于替换 {{user}}
    user_name = ""
    try:
        settings = load_settings()
        pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else bool(getattr(settings, "pureAiMode", False))
        if pure_ai_mode:
            # 纯 AI 模式不注入 persona，但为了避免 {{user}} 残留，使用通用称呼
            user_name = "用户"
        elif settings.selectedPersonaId and settings.userPersonas:
            selected_persona = next((p for p in settings.userPersonas if p.id == settings.selectedPersonaId), None)
            if selected_persona:
                user_name = selected_persona.name
    except Exception:
        pass
    
    # 单聊时：如果角色有首句，自动添加为 assistant 的第一条消息
    if not is_group:
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
    else:
        # 群聊时：可选择启用某成员的 firstMessage 作为开场背景
        if req.firstMessageCharacterId:
            if req.firstMessageCharacterId not in chat.memberIds:
                raise HTTPException(status_code=400, detail="firstMessageCharacterId is not a member of this group")
            try:
                first_char = load_character(req.firstMessageCharacterId)
                if first_char.firstMessage and first_char.firstMessage.strip():
                    first_msg = first_char.firstMessage.strip()
                    if user_name:
                        first_msg = _replace_user_placeholder(first_msg, user_name)
                    chat.messages.append(ChatMessage(
                        role="assistant",
                        content=first_msg,
                        characterId=req.firstMessageCharacterId
                    ))
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="firstMessageCharacter not found")
    
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
    if req.groupDelay is not None:
        chat.groupDelay = req.groupDelay
    if req.memberSettings is not None:
        # 合并成员设置，只更新传入的成员
        for member_id, settings in req.memberSettings.items():
            chat.memberSettings[member_id] = settings
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


# ========== 群成员管理 ==========


@router.post("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def add_member(chat_id: str, member_id: str) -> Chat:
    """添加群成员"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can add members")
    
    # 检查角色是否存在
    try:
        load_character(member_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")
    
    # 添加成员（如果不存在）
    if member_id not in chat.memberIds:
        chat.memberIds.append(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat


@router.delete("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def remove_member(chat_id: str, member_id: str) -> Chat:
    """移除群成员"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can remove members")
    
    # 移除成员
    if member_id in chat.memberIds:
        chat.memberIds.remove(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat


