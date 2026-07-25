"""
AI助手路由模块

提供AI助手功能，支持工具调用、文件操作、聊天上下文访问等。

主要功能：
    - POST /assistant/stream: 流式AI助手对话（支持工具调用）
    - GET /assistant/settings: 获取助手设置
    - PUT /assistant/settings: 更新助手设置
    - GET /assistant/chat: 获取助手聊天记录
    - POST /assistant/reset: 重置助手聊天
    - GET /assistant/workspace/character-card: 获取工作空间角色卡
    - PUT /assistant/workspace/character-card: 保存工作区角色卡草稿
    - PUT /assistant/chat/messages/{message_id}: 更新助手消息
    - DELETE /assistant/chat/messages/{message_id}: 删除助手消息

主要函数：
    - stream_assistant: 流式AI助手对话
    - get_assistant_settings: 获取助手设置
    - put_assistant_settings: 更新助手设置
    - get_assistant_chat: 获取助手聊天记录
    - reset_assistant: 重置助手聊天
    - get_workspace_character_card: 获取工作空间角色卡
    - put_workspace_character_card: 保存工作空间角色卡草稿
    - update_assistant_message: 更新助手消息
    - delete_assistant_message: 删除助手消息

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入llm/openai_compat.py、schemas.py的助手相关模型和storage.py
    - 依赖：依赖llm/openai_compat.py、schemas.py和storage.py
    - 位置：路由层，处理AI助手相关的HTTP请求
"""

from __future__ import annotations

import base64
import json
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.assistant import load_agent_system_prompt
from app.errors import AppError, app_error_response
from app.request_context import REQUEST_ID_HEADER, get_request_id, new_request_id
from app.sse import sse_done, sse_meta, sse_terminal_error
from app.attachment_policy import (
    ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES,
    ASSISTANT_TEXT_ATTACHMENT_MAX_BYTES,
    assistant_attachment_kind,
)
from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.result import compact_tool_result_json_for_llm
from app.services.assistant_agent import (
    AssistantAgentRunContext,
    AssistantAgentService,
)
from app.llm.preset_resolve import LlmPresetResolveError, resolve_llm_preset_credentials
from app.services.user_message_content import build_user_message_content
from app.schemas import (
    AssistantAppendRole,
    build_reasoning_request_config,
    filter_reasoning_extra_body_for_upstream,
    AssistantAttachment,
    AssistantChat,
    AssistantSettings,
    AssistantSettingsUpdate,
    Chat,
    CharacterCard,
    ChatMessage,
    UpdateMessageRequest,
)
from app.storage import (
    assistant_attachment_path,
    clear_assistant_chat_attachments,
    clear_workspace_session_attachments,
    load_assistant_attachment_bytes,
    save_workspace_character_card,
    workspace_character_card_path,
    clear_assistant_chat,
    clear_assistant_chat_for_chat,
    clear_assistant_workspace_chat,
    delete_assistant_workspace_chat,
    load_assistant_chat,
    load_assistant_chat_for_chat,
    load_assistant_workspace_chat,
    load_assistant_settings,
    load_chat,
    load_chat_memory,
    load_character,
    load_settings,
    save_assistant_chat,
    save_assistant_chat_for_chat,
    save_assistant_workspace_chat,
    save_assistant_attachment,
    mark_last_message_memory_updated,
    save_chat,
    save_chat_memory,
    save_assistant_settings,
)
from app.tokenizer_service import trim_assistant_openai_messages_to_context


router = APIRouter(tags=["assistant"])


def _resolve_assistant_credentials(settings: Any, *, model: str, preset_id: str | None) -> tuple[str, str]:
    try:
        credentials = resolve_llm_preset_credentials(settings, model=model, explicit_preset_id=preset_id)
    except LlmPresetResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return credentials.base_url, credentials.api_key


class AssistantStreamRequest(BaseModel):
    """
    AI助手流式请求模型
    
    主要属性：
        userMessage: 用户消息
        model: 模型名称（可选）
        temperature: 温度参数（可选）
        appendUserMessage: 是否追加用户消息到历史
        chatId: 聊天会话ID（可选）
        allowWriteMemory: 是否允许写入长期记忆（可选）
        scope: 作用域（workspace/chat，可选）
    """
    userMessage: str
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    appendUserMessage: bool | None = True
    chatId: str | None = None
    allowWriteMemory: bool | None = None
    allowDestructiveTools: bool | None = None
    allowWebSearch: bool | None = None
    maxToolTurns: int | None = Field(default=None, ge=1)
    maxToolsPerTurn: int | None = Field(default=None, ge=1)
    scope: str | None = None
    attachments: list[AssistantAttachment] = Field(default_factory=list)


class AssistantAttachmentUploadItem(BaseModel):
    fileData: str
    mimeType: str
    originalName: str | None = None


class AssistantAttachmentIngestRequest(BaseModel):
    scope: str
    chatId: str | None = None
    workspaceSessionId: str | None = None
    files: list[AssistantAttachmentUploadItem] = Field(default_factory=list)


class AssistantAttachmentIngestResponse(BaseModel):
    attachments: list[AssistantAttachment] = Field(default_factory=list)
    workspaceSessionId: str | None = None


class WorkspaceSessionCleanupRequest(BaseModel):
    sessionId: str


def _sse(event: str, data_obj: dict) -> str:
    """
    构建Server-Sent Events格式的字符串
    
    Args:
        event: 事件类型
        data_obj: 数据对象
    
    Returns:
        str: SSE格式的字符串
    """
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


def _load_chat_context(chat_id: str) -> Chat | None:
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        return None


def _reasoning_from_msg(m: ChatMessage) -> str | None:
    if getattr(m, "reasoningContent", None):
        s = (m.reasoningContent or "").strip()
        if s:
            return s
    extra = getattr(m, "model_extra", None) or {}
    if isinstance(extra, dict) and extra.get("reasoning_content"):
        s = str(extra["reasoning_content"]).strip()
        if s:
            return s
    return None


def _attachment_display_name(attachment: AssistantAttachment) -> str:
    return (attachment.originalName or attachment.filename or attachment.id or "未命名附件").strip() or "未命名附件"


def _assistant_user_message_content(message: ChatMessage) -> str | list[dict[str, Any]]:
    text_attachments: list[tuple[str, str]] = []
    image_items: list[tuple[bytes, str]] = []
    for attachment in getattr(message, "attachments", []) or []:
        if attachment.kind == "text":
            try:
                raw = load_assistant_attachment_bytes(attachment)
                text_attachments.append((_attachment_display_name(attachment), raw.decode("utf-8")))
            except FileNotFoundError:
                text_attachments.append((_attachment_display_name(attachment), "[附件已缺失]"))
        elif attachment.kind == "image":
            try:
                image_items.append((load_assistant_attachment_bytes(attachment), attachment.mimeType or "image/png"))
            except FileNotFoundError:
                continue
    return build_user_message_content(
        message.content or "",
        text_attachments=text_attachments,
        image_items=image_items,
        image_fallback_mode=False,
    )


def _assistant_messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """
    将持久化的助手 ChatMessage 列表重建为发给上游的 OpenAI 风格 messages。
    含 assistant.tool_calls、role=tool + tool_call_id；旧版仅 toolTrace/toolRecord 的仍用 system 摘要，不伪造 id。
    """
    out: list[dict[str, Any]] = []
    _LEGACY_TOOL_TRACE_MAX = 2000
    for m in messages:
        if m.role == "reasoning":
            rc = (m.content or "").strip()
            if rc:
                out.append({"role": "assistant", "content": "", "reasoning_content": rc})
            continue

        if m.role == "tool":
            tid = (getattr(m, "tool_call_id", None) or "").strip()
            if tid:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": m.content or "",
                    }
                )
            else:
                raw = (m.content or "").strip()
                if raw:
                    text = raw if len(raw) <= _LEGACY_TOOL_TRACE_MAX else raw[:_LEGACY_TOOL_TRACE_MAX] + "…"
                    out.append({"role": "system", "content": f"[tool message missing tool_call_id] {text}"})
            continue

        if m.role == "assistant" and getattr(m, "tool_calls", None):
            d: dict[str, Any] = {
                "role": "assistant",
                "content": m.content or "",
                "tool_calls": m.tool_calls,
            }
            rc = _reasoning_from_msg(m)
            if rc:
                d["reasoning_content"] = rc
            out.append(d)
            continue

        if getattr(m, "toolTrace", False) and not getattr(m, "toolRecord", None):
            raw = (m.content or "").strip()
            if raw:
                text = raw if len(raw) <= _LEGACY_TOOL_TRACE_MAX else raw[:_LEGACY_TOOL_TRACE_MAX] + "…"
                out.append({"role": "system", "content": text})
            continue

        tr = getattr(m, "toolRecord", None)
        if isinstance(tr, dict):
            out.append({"role": "system", "content": json.dumps(tr, ensure_ascii=False)})
            continue

        msg_dict: dict[str, Any] = {
            "role": m.role,
            "content": _assistant_user_message_content(m) if m.role == "user" else m.content,
        }
        if m.role == "assistant":
            rc = _reasoning_from_msg(m)
            if rc:
                msg_dict["reasoning_content"] = rc
        out.append(msg_dict)
    return out


def _compact_tool_result_contents_for_llm(messages: list[dict[str, Any]]) -> None:
    """在进入模型前压缩 role=tool 的 ToolResult JSON；与 trim 顺序：先 compact 再按段裁剪。"""
    for m in messages:
        if m.get("role") != "tool":
            continue
        c = m.get("content")
        if isinstance(c, str) and c:
            m["content"] = compact_tool_result_json_for_llm(c)


def _normalize_assistant_chat_for_save(chat: AssistantChat) -> None:
    """保存前校验/规范化助手消息；非法组合 fast-fail，禁止脏对象落盘。"""
    normalized: list[ChatMessage] = []
    for index, m in enumerate(chat.messages):
        try:
            normalized.append(ChatMessage.model_validate(m.model_dump(mode="json")))
        except Exception as exc:
            msg_id = getattr(m, "id", None)
            role = getattr(m, "role", None)
            raise AppError(
                code="assistant_message_invalid",
                message="助手消息结构无效，已阻止写入磁盘",
                detail=f"index={index} id={msg_id!s} role={role!s}: {type(exc).__name__}: {exc}",
                source="assistant.chat.save",
                status_code=400,
                suggested_action="检查助手会话中的 tool/assistant 消息字段后重试",
            ) from exc
    chat.messages = normalized


def _ensure_system_prompt(messages: list[dict[str, Any]], prompt: str) -> None:
    """
    确保消息列表中有system prompt
    
    如果第一条消息是system，则更新其内容；否则在开头插入system消息。
    
    Args:
        messages: 消息列表（会被修改）
        prompt: 系统提示词
    """
    if not prompt or not prompt.strip():
        return
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = prompt
        return
    messages.insert(0, {"role": "system", "content": prompt})


def _resolve_assistant_chat(chat_id: str | None) -> AssistantChat:
    """
    解析助手聊天记录
    
    Args:
        chat_id: 聊天会话ID（可选）
    
    Returns:
        AssistantChat: 助手聊天对象
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    if chat_id:
        try:
            return load_assistant_chat_for_chat(chat_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="chat not found")
    return load_assistant_chat()


def _save_assistant_chat(chat_id: str | None, chat: AssistantChat) -> AssistantChat:
    """
    保存助手聊天记录
    
    Args:
        chat_id: 聊天会话ID（可选）
        chat: 助手聊天对象
    
    Returns:
        AssistantChat: 保存后的助手聊天对象
    """
    if chat_id:
        return save_assistant_chat_for_chat(chat_id, chat)
    return save_assistant_chat(chat)


def _clear_assistant_chat(chat_id: str | None) -> None:
    """
    清空助手聊天记录
    
    Args:
        chat_id: 聊天会话ID（可选）
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    if chat_id:
        try:
            clear_assistant_chat_for_chat(chat_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="chat not found")
    else:
        clear_assistant_chat()


def _resolve_assistant_chat_by_scope(scope: str | None, chat_id: str | None) -> AssistantChat:
    """
    根据作用域解析助手聊天记录
    
    Args:
        scope: 作用域（workspace表示工作空间，其他表示普通聊天）
        chat_id: 聊天会话ID（可选）
    
    Returns:
        AssistantChat: 助手聊天对象
    """
    if scope == "workspace":
        return load_assistant_workspace_chat()
    return _resolve_assistant_chat(chat_id)


def _save_assistant_chat_by_scope(scope: str | None, chat_id: str | None, chat: AssistantChat) -> AssistantChat:
    """
    根据作用域保存助手聊天记录
    
    Args:
        scope: 作用域
        chat_id: 聊天会话ID（可选）
        chat: 助手聊天对象
    
    Returns:
        AssistantChat: 保存后的助手聊天对象
    """
    _normalize_assistant_chat_for_save(chat)
    if scope == "workspace":
        return save_assistant_workspace_chat(chat)
    return _save_assistant_chat(chat_id, chat)


def _clear_assistant_chat_by_scope(scope: str | None, chat_id: str | None) -> None:
    """
    根据作用域清空助手聊天记录
    
    Args:
        scope: 作用域
        chat_id: 聊天会话ID（可选）
    """
    if scope == "workspace":
        clear_assistant_workspace_chat()
    else:
        _clear_assistant_chat(chat_id)


def _build_chat_participants_prompt(chat_id: str | None) -> str | None:
    """
    构建聊天参与者提示词
    
    Args:
        chat_id: 聊天会话ID（可选）
    
    Returns:
        str | None: 参与者提示词，不存在返回None
    """
    if not chat_id:
        return None
    chat = _load_chat_context(chat_id)
    if chat is None:
        return None
    participant_ids = chat.memberIds if chat.isGroup else [chat.characterId]
    lines = ["当前会话参与角色（含 id）："]
    for idx, cid in enumerate(participant_ids, start=1):
        try:
            card = load_character(cid)
            name = card.name or ""
        except FileNotFoundError:
            name = ""
        lines.append(f"{idx}. {name} (id: {cid})")
    return "\n".join(lines)


def _validate_assistant_attachment_upload(item: AssistantAttachmentUploadItem) -> tuple[str, bytes]:
    kind = assistant_attachment_kind(item.mimeType, item.originalName)
    if kind is None:
        raise HTTPException(status_code=400, detail=f"unsupported attachment type: {item.originalName or item.mimeType or 'unknown'}")
    raw = item.fileData
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid attachment fileData") from exc
    size_limit = ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES if kind == "image" else ASSISTANT_TEXT_ATTACHMENT_MAX_BYTES
    if len(data) > size_limit:
        raise HTTPException(status_code=400, detail=f"attachment too large: {item.originalName or item.mimeType or 'unknown'}")
    if kind == "text":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"attachment must be utf-8: {item.originalName or item.mimeType or 'unknown'}") from exc
    return kind, data


def _find_assistant_attachment(
    attachment_id: str,
    *,
    scope: str | None,
    chat_id: str | None,
) -> AssistantAttachment | None:
    chat = _resolve_assistant_chat_by_scope(scope, chat_id)
    for message in chat.messages:
        for attachment in getattr(message, "attachments", []) or []:
            if attachment.id == attachment_id:
                return attachment
    return None


@router.get("/assistant/workspace/character-card", response_model=CharacterCard)
def get_workspace_character_card() -> CharacterCard:
    """
    获取工作空间角色卡草稿。

    缺失返回 data_not_found；损坏返回 data_corrupted；成功直接返回 CharacterCard。
    """
    card_path = workspace_character_card_path()
    if not card_path.exists():
        raise AppError(
            code="data_not_found",
            message="工作区角色卡草稿不存在",
            detail=card_path.name,
            source="assistant.workspace.character_card",
            status_code=404,
            suggested_action="创建新角色或先保存草稿后再读取",
        )
    try:
        raw = json.loads(card_path.read_text(encoding="utf-8"))
        return CharacterCard.model_validate(raw)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="data_corrupted",
            message="工作区角色卡草稿已损坏或结构无效",
            detail=f"{card_path.name}: {type(exc).__name__}",
            source="assistant.workspace.character_card",
            status_code=500,
            suggested_action="删除或修复 data/ai_workspace/character_card.json 后重试",
        ) from exc


@router.put("/assistant/workspace/character-card", response_model=CharacterCard)
def put_workspace_character_card(card: CharacterCard) -> CharacterCard:
    """
    保存工作区角色卡草稿

    写入 data/ai_workspace/character_card.json，供助手工具 workspace_write_file 与前端共用同一暂存位置。
    """
    return save_workspace_character_card(card)


@router.post("/assistant/attachments/ingest", response_model=AssistantAttachmentIngestResponse)
def ingest_assistant_attachments(req: AssistantAttachmentIngestRequest) -> AssistantAttachmentIngestResponse:
    """将助手附件写入 ai_workspace/ingest，并返回稳定附件元数据。"""
    scope = (req.scope or "").strip()
    if scope not in {"chat", "workspace"}:
        raise HTTPException(status_code=400, detail="invalid scope")
    if scope == "chat":
        chat_id = (req.chatId or "").strip()
        if not chat_id:
            raise HTTPException(status_code=400, detail="chatId is required for chat scope")
        if _load_chat_context(chat_id) is None:
            raise HTTPException(status_code=404, detail="chat not found")
        storage_scope = "assistant_chat"
        storage_key = chat_id
        workspace_session_id = None
    else:
        storage_scope = "workspace_session"
        storage_key = (req.workspaceSessionId or "").strip() or uuid4().hex
        workspace_session_id = storage_key

    attachments: list[AssistantAttachment] = []
    for item in req.files or []:
        kind, data = _validate_assistant_attachment_upload(item)
        attachments.append(
            save_assistant_attachment(
                data=data,
                kind=kind,
                storage_scope=storage_scope,
                storage_key=storage_key,
                mime_type=item.mimeType,
                original_name=item.originalName,
            )
        )
    return AssistantAttachmentIngestResponse(
        attachments=attachments,
        workspaceSessionId=workspace_session_id,
    )


@router.get("/assistant/attachments/{attachment_id}")
def get_assistant_attachment(
    attachment_id: str,
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    storageScope: str | None = Query(default=None),
    storageKey: str | None = Query(default=None),
    filename: str | None = Query(default=None),
    mimeType: str | None = Query(default=None),
    kind: str | None = Query(default=None),
) -> FileResponse:
    """读取助手消息附件。工作区会在会话清理后返回 404，供前端降级展示。"""
    attachment = _find_assistant_attachment(attachment_id, scope=scope, chat_id=chatId)
    if attachment is None and storageScope and storageKey and filename and mimeType and kind in {"image", "text"}:
      attachment = AssistantAttachment(
          id=attachment_id,
          kind=kind,
          storageScope=storageScope,
          storageKey=storageKey,
          filename=filename,
          mimeType=mimeType,
          size=0,
      )
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    try:
        file_path = assistant_attachment_path(attachment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="attachment file not found")
    return FileResponse(file_path, media_type=attachment.mimeType or "application/octet-stream")


@router.post("/assistant/workspace/session/cleanup")
def cleanup_workspace_session(req: WorkspaceSessionCleanupRequest) -> dict[str, Any]:
    """按 sessionId 删除工作区临时附件目录。"""
    clear_workspace_session_attachments(req.sessionId)
    return {"ok": True}


@router.get(
    "/assistant/settings",
    response_model=AssistantSettings,
    response_model_exclude={"prompt"},
)
def get_assistant_settings() -> AssistantSettings:
    """
    获取AI助手设置（响应中不包含 prompt）。
    
    Returns:
        AssistantSettings: 助手设置对象
    """
    return load_assistant_settings()


@router.put(
    "/assistant/settings",
    response_model=AssistantSettings,
    response_model_exclude={"prompt"},
)
def put_assistant_settings(body: AssistantSettingsUpdate) -> AssistantSettings:
    """
    更新AI助手设置：请求体中未出现的字段保留原值。系统提示词由 AGENT.md 提供，不依赖本接口。
    
    Args:
        body: 部分字段更新
    
    Returns:
        AssistantSettings: 保存后的设置对象（响应中不包含 prompt）
    """
    existing = load_assistant_settings()
    patch = body.model_dump(exclude_unset=True)
    merged = existing.model_copy(update=patch)
    return save_assistant_settings(merged)


@router.get("/assistant/chat", response_model=AssistantChat)
def get_assistant_chat(
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
    """
    获取AI助手聊天记录
    
    Args:
        chatId: 聊天会话ID（可选）
        scope: 作用域（workspace/chat，可选）
    
    Returns:
        AssistantChat: 助手聊天对象
    """
    return _resolve_assistant_chat_by_scope(scope, chatId)


class AppendAssistantMessageRequest(BaseModel):
    """追加助手消息请求"""

    role: AssistantAppendRole = "assistant"
    content: str = ""
    reasoningContent: str | None = None
    reasoningDurationSec: float | None = None


@router.post("/assistant/chat/messages", response_model=AssistantChat)
def append_assistant_message(
    req: AppendAssistantMessageRequest,
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
    """
    向助手聊天追加一条消息（用于流式中断时保存截断内容）。
    """
    chat = _resolve_assistant_chat_by_scope(scope, chatId)
    if req.role == "reasoning":
        chat.messages.append(
            ChatMessage(
                role="reasoning",
                content=req.content or "",
                reasoningDurationSec=req.reasoningDurationSec,
            )
        )
    else:
        chat.messages.append(
            ChatMessage(
                role=req.role,
                content=req.content,
                reasoningContent=req.reasoningContent,
                reasoningDurationSec=req.reasoningDurationSec,
            )
        )
    return _save_assistant_chat_by_scope(scope, chatId, chat)


@router.post("/assistant/reset")
def reset_assistant(
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    """
    重置AI助手聊天
    
    清空聊天记录；聊天作用域只清理自身 ingest 附件目录，不影响整个 ai_workspace。
    
    Args:
        chatId: 聊天会话ID（可选）
        scope: 作用域（可选）
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    _clear_assistant_chat_by_scope(scope, chatId)
    if scope != "workspace":
        clear_assistant_chat_attachments(chatId)
    return {"ok": True}


@router.post("/assistant/workspace/chat/delete")
def delete_workspace_chat() -> dict:
    """
    删除工作空间聊天记录
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_assistant_workspace_chat()
    return {"ok": True}


@router.put("/assistant/chat/messages/{message_id}")
def update_assistant_message(
    message_id: str,
    req: UpdateMessageRequest,
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
    """
    更新AI助手消息
    
    Args:
        message_id: 消息ID
        req: 更新请求对象
        chatId: 聊天会话ID（可选）
        scope: 作用域（可选）
    
    Returns:
        AssistantChat: 更新后的助手聊天对象
    
    Raises:
        HTTPException: 消息不存在时抛出404错误
    """
    chat = _resolve_assistant_chat_by_scope(scope, chatId)
    for m in chat.messages:
        if m.id == message_id:
            m.role = req.role
            m.content = req.content
            _save_assistant_chat_by_scope(scope, chatId, chat)
            return chat
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="message not found")


@router.delete("/assistant/chat/messages/{message_id}")
def delete_assistant_message(
    message_id: str,
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
    """
    删除AI助手消息
    
    Args:
        message_id: 消息ID
        chatId: 聊天会话ID（可选）
        scope: 作用域（可选）
    
    Returns:
        AssistantChat: 更新后的助手聊天对象
    """
    chat = _resolve_assistant_chat_by_scope(scope, chatId)
    new_msgs = [m for m in chat.messages if m.id != message_id]
    chat.messages = new_msgs
    _save_assistant_chat_by_scope(scope, chatId, chat)
    return chat


@router.post("/assistant/stream", response_model=None)
async def stream_assistant(req: AssistantStreamRequest, request: Request):
    """
    流式 AI 助手对话。

    支持工具调用、多轮对话、推理内容等；作用域可为 workspace 或 chat。
    长期记忆写入与破坏性工具是否可用仅由请求体中的 allowWriteMemory、
    allowDestructiveTools 决定（工作区作用域下不会开启记忆写入）。

    Args:
        req: 流式请求对象
        request: FastAPI 请求（用于 requestId）

    Returns:
        StreamingResponse | JSONResponse: SSE 流式响应或非流 JSON / 错误 envelope
    """
    request_id = getattr(request.state, "request_id", None) or get_request_id() or new_request_id()
    settings = load_settings()
    assistant_settings = load_assistant_settings()
    scope = req.scope
    chat_id = None if scope == "workspace" else req.chatId
    chat = _resolve_assistant_chat_by_scope(scope, chat_id)

    model = req.model or assistant_settings.model or settings.llm.defaultModel
    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    temperature = req.temperature if req.temperature is not None else assistant_settings.temperature
    if thinking_enabled:
        temperature = None

    preset_id = assistant_settings.presetId
    base_url, api_key = _resolve_assistant_credentials(settings, model=model, preset_id=preset_id)

    existing_messages = chat.messages or []
    
    if req.appendUserMessage:
        new_user_msg = ChatMessage(
            role="user",
            content=req.userMessage,
            attachments=list(req.attachments or []),
        )
        existing_messages.append(new_user_msg)
        chat.messages = existing_messages
        _save_assistant_chat_by_scope(scope, chat_id, chat)

    conversation = _assistant_messages_to_openai(list(existing_messages))
    _compact_tool_result_contents_for_llm(conversation)
    context_size = getattr(assistant_settings, "context_size", None)
    if context_size and context_size >= 1:
        conversation = trim_assistant_openai_messages_to_context(conversation, context_size, None)

    llm_msgs: list[dict[str, Any]] = []
    _ensure_system_prompt(llm_msgs, load_agent_system_prompt())
    participants_prompt = _build_chat_participants_prompt(chat_id)
    if participants_prompt:
        llm_msgs.append({"role": "system", "content": participants_prompt})
    llm_msgs.extend(conversation)

    allow_write_memory = bool(req.allowWriteMemory) if req.allowWriteMemory is not None else False
    if scope == "workspace":
        allow_write_memory = False
    allow_destructive_tools = bool(req.allowDestructiveTools) if req.allowDestructiveTools is not None else False
    allow_web_search = bool(req.allowWebSearch) if req.allowWebSearch is not None else False
    tool_ctx = AssistantToolContext(
        chat_id=chat_id,
        scope=scope,
        allow_write_memory=allow_write_memory,
        allow_destructive_tools=allow_destructive_tools,
        allow_web_search=allow_web_search,
        assistant_settings=assistant_settings,
    )
    extra_body = filter_reasoning_extra_body_for_upstream(model, reasoning_cfg["extra_body"])
    agent_ctx = AssistantAgentRunContext(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        messages=llm_msgs,
        extra_body=extra_body,
        tool_ctx=tool_ctx,
        load_chat=lambda: _resolve_assistant_chat_by_scope(scope, chat_id),
        save_chat=lambda assistant_chat: _save_assistant_chat_by_scope(scope, chat_id, assistant_chat),
        max_tool_turns=req.maxToolTurns or assistant_settings.maxToolTurns or 8,
        max_tools_per_turn=req.maxToolsPerTurn or assistant_settings.maxToolsPerTurn,
    )
    agent = AssistantAgentService(agent_ctx)

    # 非流式：与全局设置 streamEnabled 一致，返回 JSON
    if not getattr(settings, "streamEnabled", True):
        try:
            result = await agent.run_nonstream()
        except AppError as exc:
            return app_error_response(exc, request_id)
        return JSONResponse(
            {
                "ok": True,
                "stream": False,
                "content": result.content,
                "messageId": result.message_id,
                "toolTraces": result.tool_traces,
                "toolRecords": result.tool_records,
                "card": result.card,
                "worldbookUpdated": result.worldbook_updated,
                "chatOverridesUpdated": result.chat_overrides_updated,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )

    async def event_iter() -> AsyncIterator[str]:
        """
        流式事件迭代器

        使用 stream_chat_completions 逐块推送 reasoning 与 content，实现打字机效果。
        支持多轮工具调用；错误事件携带统一 ErrorEnvelope。
        """
        yield sse_meta(
            request_id=request_id,
            provider="openai_compatible",
            protocol="openai_compatible_chat",
            resolved_model=model,
        )
        try:
            async for event in agent.iter_events():
                if event.kind == "error":
                    yield _sse("error", event.data)
                    return
                if event.kind == "done":
                    yield sse_done(event.data)
                    return
                yield _sse(event.kind, event.data)
        except Exception as exc:
            yield sse_terminal_error(
                exc,
                request_id=request_id,
                source="assistant.stream",
                default_code="assistant_failed",
                default_message="助手流式执行失败",
                provider="openai_compatible",
                protocol="openai_compatible_chat",
            )

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            REQUEST_ID_HEADER: request_id,
        },
    )
