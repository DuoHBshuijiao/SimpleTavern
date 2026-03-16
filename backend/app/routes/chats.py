"""
聊天管理路由模块

提供聊天会话的CRUD操作和消息管理API端点，支持单聊和群聊两种模式。

主要功能：
    - GET /chats: 获取指定角色的所有聊天会话
    - GET /chats/groups: 获取所有群聊会话
    - POST /chats: 创建新聊天会话（支持单聊和群聊）
    - GET /chats/{chat_id}: 获取指定聊天会话
    - PUT /chats/{chat_id}: 更新聊天会话信息
    - DELETE /chats/{chat_id}: 删除聊天会话
    - POST /chats/{chat_id}/messages: 追加消息
    - PUT /chats/{chat_id}/messages/{message_id}: 更新消息
    - DELETE /chats/{chat_id}/messages/{message_id}: 删除消息
    - POST /chats/{chat_id}/members/{member_id}: 添加群成员
    - DELETE /chats/{chat_id}/members/{member_id}: 移除群成员

主要函数：
    - get_chats: 获取指定角色的聊天列表
    - get_group_chats: 获取所有群聊
    - create_chat: 创建聊天会话
    - get_chat: 获取聊天会话
    - update_chat: 更新聊天会话
    - append_message: 追加消息
    - update_message: 更新消息
    - delete_message: 删除消息
    - remove_chat: 删除聊天会话
    - add_member: 添加群成员
    - remove_member: 移除群成员

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入schemas.py的聊天相关模型和storage.py的聊天管理函数
    - 依赖：依赖schemas.py和storage.py
    - 位置：路由层，处理聊天相关的HTTP请求
"""

from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.placeholders import replace_placeholders_in_text
from app.schemas import AppendMessageRequest, Chat, ChatImageAttachment, ChatMessage, CreateChatRequest, UpdateChatRequest, UpdateMessageRequest
from app.storage import (
    chat_image_path,
    delete_chat,
    delete_chat_image,
    delete_message_images,
    list_chats,
    list_group_chats,
    load_character,
    load_chat,
    load_settings,
    mark_last_message_memory_updated,
    save_chat,
    save_chat_image,
)

router = APIRouter(tags=["chats"])


def _now_iso() -> str:
    """
    获取当前时间的ISO格式字符串
    
    Returns:
        str: 当前时间的ISO格式字符串
    """
    return datetime.now().astimezone().isoformat()


def _merge_overrides(existing: Chat, incoming: UpdateChatRequest) -> None:
    """
    合并聊天覆盖设置
    
    将更新请求中的overrides合并到现有聊天对象中。
    对于params字段，只覆盖非None的值，避免一次更新清空所有旧参数。
    
    Args:
        existing: 现有的聊天对象（会被修改）
        incoming: 更新请求对象
    """
    if incoming.overrides is None:
        return
    ov = incoming.overrides
    if ov.prompt is not None:
        existing.overrides.prompt = ov.prompt
    if getattr(ov, "longTermMemory", None) is not None:
        existing.overrides.longTermMemory = ov.longTermMemory
    if hasattr(ov, "contextStartMessageId"):
        existing.overrides.contextStartMessageId = ov.contextStartMessageId
    if getattr(ov, "pureAiMode", None) is not None:
        existing.overrides.pureAiMode = ov.pureAiMode
    if hasattr(ov, "presetId"):
        existing.overrides.presetId = ov.presetId
    if hasattr(ov, "draftHelp"):
        if existing.overrides.draftHelp is None:
            existing.overrides.draftHelp = ov.draftHelp
        elif hasattr(ov.draftHelp, "context_message_limit"):
            existing.overrides.draftHelp.context_message_limit = ov.draftHelp.context_message_limit

    for key in ("model", "temperature", "top_p", "max_tokens", "context_size"):
        val = getattr(ov.params, key, None)
        # context_size 允许显式设为 None 表示“未启用”；其他参数仅在有值时覆盖
        if key == "context_size" or val is not None:
            setattr(existing.overrides.params, key, val)


class UploadChatImageItem(BaseModel):
    imageData: str
    mimeType: str = "image/png"
    originalName: str | None = None
    width: int | None = None
    height: int | None = None


class UploadChatImagesRequest(BaseModel):
    images: list[UploadChatImageItem] = Field(default_factory=list)


class UploadChatImagesResponse(BaseModel):
    images: list[ChatImageAttachment] = Field(default_factory=list)


class ChatSearchHit(BaseModel):
    messageId: str
    messageIndex: int
    snippet: str


class ChatSearchResponse(BaseModel):
    query: str
    total: int
    hits: list[ChatSearchHit] = Field(default_factory=list)


@router.get("/chats", response_model=list[Chat])
def get_chats(characterId: str = Query(...)) -> list[Chat]:
    """
    获取指定角色的所有聊天会话
    
    Args:
        characterId: 角色ID（查询参数）
    
    Returns:
        list[Chat]: 聊天会话列表，按更新时间倒序
    """
    return list_chats(characterId)


@router.get("/chats/groups", response_model=list[Chat])
def get_group_chats() -> list[Chat]:
    """
    获取所有群聊会话
    
    Returns:
        list[Chat]: 群聊会话列表，按更新时间倒序
    """
    return list_group_chats()


@router.post("/chats", response_model=Chat)
def create_chat(req: CreateChatRequest) -> Chat:
    """
    创建新聊天会话
    
    支持单聊和群聊两种模式。对于单聊，如果角色有首条消息，会自动添加为assistant的第一条消息。
    对于群聊，可以选择启用某个成员的首条消息作为开场。
    会自动处理用户Persona的绑定和{{user}}占位符的替换。
    
    Args:
        req: 创建聊天请求对象
    
    Returns:
        Chat: 创建后的聊天对象
    
    Raises:
        HTTPException: 群聊时firstMessageCharacterId不是成员或角色不存在时抛出400或404错误
    """
    is_group = req.isGroup
    
    if is_group:
        title = req.title or "新群聊"
        member_ids = req.memberIds or []
        if req.characterId and req.characterId not in member_ids:
            member_ids = [req.characterId] + member_ids
        chat = Chat(
            characterId=req.characterId,
            title=title,
            isGroup=True,
            memberIds=member_ids
        )
    else:
        chat = Chat(characterId=req.characterId, title=req.title or "新对话")
    
    chat.overrides.pureAiMode = req.pureAiMode
    
    if is_group and req.memberSettings:
        for member_id, s in req.memberSettings.items():
            chat.memberSettings[member_id] = s
    
    chat.createdAt = _now_iso()
    chat.updatedAt = _now_iso()
    
    user_name = ""
    pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else False
    try:
        settings = load_settings()
        pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else bool(getattr(settings, "pureAiMode", False))
        if pure_ai_mode:
            user_name = "用户"
        else:
            persona_id = req.userPersonaId or settings.selectedPersonaId
            selected_persona = None
            if persona_id and settings.userPersonas:
                selected_persona = next((p for p in settings.userPersonas if p.id == persona_id), None)
            if selected_persona:
                user_name = selected_persona.name
        if not user_name:
            user_name = "用户"
    except Exception:
        pass

    if pure_ai_mode:
        chat.userPersonaId = None
    else:
        chat.userPersonaId = req.userPersonaId or (settings.selectedPersonaId if "settings" in locals() else None)
    
    if not is_group:
        try:
            character = load_character(req.characterId)
            if character.firstMessage and character.firstMessage.strip():
                first_msg = character.firstMessage.strip()
                first_msg = replace_placeholders_in_text(
                    first_msg,
                    char_name=(character.name or "角色"),
                    user_name=user_name or "用户",
                )
                chat.messages.append(ChatMessage(
                    role="assistant",
                    content=first_msg
                ))
        except FileNotFoundError:
            pass
    else:
        if req.firstMessageCharacterId:
            if req.firstMessageCharacterId not in chat.memberIds:
                raise HTTPException(status_code=400, detail="firstMessageCharacterId is not a member of this group")
            try:
                first_char = load_character(req.firstMessageCharacterId)
                if first_char.firstMessage and first_char.firstMessage.strip():
                    first_msg = first_char.firstMessage.strip()
                    first_msg = replace_placeholders_in_text(
                        first_msg,
                        char_name=(first_char.name or "角色"),
                        user_name=user_name or "用户",
                    )
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
    """
    获取指定聊天会话
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        Chat: 聊天对象
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")


@router.get("/chats/{chat_id}/search", response_model=ChatSearchResponse)
def search_chat(chat_id: str, q: str = Query(..., min_length=1)) -> ChatSearchResponse:
    """在当前会话正文中全文检索。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    query = q.strip()
    if not query:
        return ChatSearchResponse(query=q, total=0, hits=[])
    query_lower = query.lower()
    hits: list[ChatSearchHit] = []
    for idx, msg in enumerate(chat.messages):
        content = (msg.content or "").strip()
        if not content:
            continue
        pos = content.lower().find(query_lower)
        if pos < 0:
            continue
        start = max(0, pos - 32)
        end = min(len(content), pos + len(query) + 64)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        hits.append(ChatSearchHit(
            messageId=msg.id,
            messageIndex=idx,
            snippet=snippet,
        ))
        if len(hits) >= 300:
            break
    return ChatSearchResponse(query=query, total=len(hits), hits=hits)


@router.put("/chats/{chat_id}", response_model=Chat)
def update_chat(chat_id: str, req: UpdateChatRequest) -> Chat:
    """
    更新聊天会话
    
    支持更新标题、群聊延迟、成员列表（仅重排）、成员设置、用户Persona和覆盖设置。
    对于群聊的memberIds更新，仅允许重排（成员集合必须一致）。
    
    Args:
        chat_id: 聊天会话ID
        req: 更新请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在、非群聊尝试更新memberIds或成员集合不一致时抛出错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    if req.title is not None:
        chat.title = req.title
    if req.groupDelay is not None:
        chat.groupDelay = req.groupDelay
    if req.memberIds is not None:
        if not chat.isGroup:
            raise HTTPException(status_code=400, detail="memberIds can only be updated for group chats")
        if set(req.memberIds) != set(chat.memberIds):
            raise HTTPException(status_code=400, detail="memberIds must contain the same members (reorder only)")
        chat.memberIds = req.memberIds
    if req.memberSettings is not None:
        for member_id, settings in req.memberSettings.items():
            chat.memberSettings[member_id] = settings
    if "userPersonaId" in req.model_fields_set:
        chat.userPersonaId = req.userPersonaId
    # 仅在本次请求真正修改了长期记忆内容时才标记 memoryUpdatedAfterThis，避免仅切换模型等操作时误触发
    incoming_memory = getattr(req.overrides, "longTermMemory", None) if req.overrides else None
    current_memory = getattr(chat.overrides, "longTermMemory", None) or ""
    memory_actually_changed = (
        incoming_memory is not None
        and (incoming_memory or "") != (current_memory or "")
    )
    _merge_overrides(chat, req)
    if memory_actually_changed:
        mark_last_message_memory_updated(chat)
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.post("/chats/{chat_id}/messages", response_model=Chat)
def append_message(chat_id: str, req: AppendMessageRequest) -> Chat:
    """
    向聊天会话追加消息
    
    Args:
        chat_id: 聊天会话ID
        req: 追加消息请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    chat.messages.append(ChatMessage(
        role=req.role,
        content=req.content,
        images=getattr(req, "images", []) or [],
        characterId=req.characterId,
        senderPersonaId=getattr(req, "senderPersonaId", None),
        senderName=getattr(req, "senderName", None),
        senderAvatar=getattr(req, "senderAvatar", None),
    ))
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.put("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def update_message(chat_id: str, message_id: str, req: UpdateMessageRequest) -> Chat:
    """
    更新聊天会话中的消息
    
    支持更新消息的角色、内容、角色ID和发送者快照信息。
    发送者快照用于在切换Persona时保持历史消息的显示一致性。
    
    Args:
        chat_id: 聊天会话ID
        message_id: 消息ID
        req: 更新消息请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天或消息不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    for m in chat.messages:
        if m.id == message_id:
            old_images = list(getattr(m, "images", []) or [])
            m.role = req.role
            m.content = req.content
            if getattr(req, "images", None) is not None:
                m.images = req.images or []
                old_ids = {img.id for img in old_images}
                new_ids = {img.id for img in (m.images or [])}
                for old_img in old_images:
                    if old_img.id not in new_ids:
                        delete_chat_image(chat, old_img)
            # 仅当客户端显式传入 characterId 时更新，避免群聊中编辑仅改内容时覆盖发言人
            if req.characterId is not None:
                m.characterId = req.characterId
            if getattr(req, "senderPersonaId", None) is not None:
                m.senderPersonaId = req.senderPersonaId
            if getattr(req, "senderName", None) is not None:
                m.senderName = req.senderName
            if getattr(req, "senderAvatar", None) is not None:
                m.senderAvatar = req.senderAvatar
            chat.updatedAt = _now_iso()
            return save_chat(chat)

    raise HTTPException(status_code=404, detail="message not found")


@router.delete("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def delete_message(chat_id: str, message_id: str) -> Chat:
    """
    删除聊天会话中的消息
    
    Args:
        chat_id: 聊天会话ID
        message_id: 消息ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天或消息不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    before = len(chat.messages)
    kept_messages: list[ChatMessage] = []
    for msg in chat.messages:
        if msg.id == message_id:
            delete_message_images(chat, msg)
            continue
        kept_messages.append(msg)
    chat.messages = kept_messages
    if len(chat.messages) == before:
        raise HTTPException(status_code=404, detail="message not found")

    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: str) -> dict:
    """
    删除聊天会话
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_chat(chat_id)
    return {"ok": True}


@router.post("/chats/{chat_id}/images", response_model=UploadChatImagesResponse)
def upload_chat_images(chat_id: str, req: UploadChatImagesRequest) -> UploadChatImagesResponse:
    """上传会话图片，返回附件元数据。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    if not req.images:
        return UploadChatImagesResponse(images=[])
    saved: list[ChatImageAttachment] = []
    for item in req.images:
        try:
            raw = item.imageData
            if "," in raw:
                raw = raw.split(",", 1)[1]
            data = base64.b64decode(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid imageData")
        attachment = save_chat_image(
            chat=chat,
            data=data,
            mime_type=item.mimeType,
            original_name=item.originalName,
            width=item.width,
            height=item.height,
        )
        saved.append(attachment)
    return UploadChatImagesResponse(images=saved)


@router.get("/chats/{chat_id}/images/{image_id}")
def get_chat_image(chat_id: str, image_id: str) -> FileResponse:
    """读取会话图片文件。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    image: ChatImageAttachment | None = None
    for msg in chat.messages:
        for img in getattr(msg, "images", []) or []:
            if img.id == image_id:
                image = img
                break
        if image:
            break
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    path = chat_image_path(chat.characterId, chat.id, image.filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file not found")
    return FileResponse(path, media_type=image.mimeType or "application/octet-stream")


@router.post("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def add_member(chat_id: str, member_id: str) -> Chat:
    """
    向群聊添加成员
    
    只能向群聊添加成员。会检查角色是否存在，如果成员已存在则不做任何操作。
    
    Args:
        chat_id: 聊天会话ID
        member_id: 要添加的角色ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在、非群聊、角色不存在时抛出相应错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can add members")
    
    try:
        load_character(member_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")
    
    if member_id not in chat.memberIds:
        chat.memberIds.append(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat


@router.delete("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def remove_member(chat_id: str, member_id: str) -> Chat:
    """
    从群聊移除成员
    
    只能从群聊移除成员。如果成员不存在则不做任何操作。
    
    Args:
        chat_id: 聊天会话ID
        member_id: 要移除的角色ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在或非群聊时抛出相应错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can remove members")
    
    if member_id in chat.memberIds:
        chat.memberIds.remove(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat
