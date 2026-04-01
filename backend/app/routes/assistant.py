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

import json
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.digest import args_digest as _tool_args_digest
from app.assistant_tools.result import compact_tool_result_json_for_llm
from app.assistant_tools.executor import build_openai_tools_list, execute_tool
from app.llm.openai_compat import chat_completions_message, stream_chat_completions
from app.schemas import (
    build_reasoning_request_config,
    filter_reasoning_extra_body_for_upstream,
    AssistantChat,
    AssistantSettings,
    AssistantSettingsUpdate,
    Chat,
    CharacterCard,
    ChatMessage,
    MainChatRole,
    UpdateMessageRequest,
)
from app.storage import (
    ai_workspace_dir,
    save_workspace_character_card,
    clear_ai_workspace,
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
    mark_last_message_memory_updated,
    save_chat,
    save_chat_memory,
    save_assistant_settings,
)
from app.tokenizer_service import trim_assistant_openai_messages_to_context


router = APIRouter(tags=["assistant"])


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
    scope: str | None = None


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


def _tool_record_payload(
    tool_name: str,
    loop_index: int,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    msg = str(result.get("message") or "")
    return {
        "toolName": tool_name,
        "loopIndex": loop_index,
        "ok": bool(result.get("ok")),
        "code": result.get("code"),
        "message": msg,
        "argsDigest": _tool_args_digest(args),
    }


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


def _normalize_tool_calls_ids(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """为每条 tool_call 补全非空 id，保证与落库的 role=tool.tool_call_id 一致。"""
    if not tool_calls:
        return []
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        tc_copy = dict(tc) if isinstance(tc, dict) else {}
        tid = str(tc_copy.get("id") or "").strip()
        if not tid:
            tid = f"call_{uuid4().hex}"
        tc_copy["id"] = tid
        out.append(tc_copy)
    return out


def _assistant_messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """
    将持久化的助手 ChatMessage 列表重建为发给上游的 OpenAI 风格 messages。
    含 assistant.tool_calls、role=tool + tool_call_id；旧版仅 toolTrace/toolRecord 的仍用 system 摘要，不伪造 id。
    """
    out: list[dict[str, Any]] = []
    _LEGACY_TOOL_TRACE_MAX = 2000
    for m in messages:
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

        msg_dict: dict[str, Any] = {"role": m.role, "content": m.content}
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
    """保存前校验/规范化助手消息，避免非法组合写入磁盘。"""
    normalized: list[ChatMessage] = []
    for m in chat.messages:
        try:
            normalized.append(ChatMessage.model_validate(m.model_dump(mode="json")))
        except Exception:
            normalized.append(m)
    chat.messages = normalized


def _clear_reasoning_content(messages: list[dict[str, Any]]) -> None:
    """
    清除消息中的reasoning_content字段
    
    Args:
        messages: 消息列表（会被修改）
    """
    for msg in messages:
        if "reasoning_content" in msg:
            msg.pop("reasoning_content", None)


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


@router.get("/assistant/workspace/character-card")
def get_workspace_character_card() -> dict[str, Any]:
    """
    获取工作空间角色卡片
    
    读取ai_workspace/character_card.json文件的内容。
    
    Returns:
        dict[str, Any]: 包含ok、error和card字段的响应
    """
    card_path = ai_workspace_dir() / "character_card.json"
    if not card_path.exists():
        return {"ok": False, "error": "not found", "card": None}
    try:
        raw = json.loads(card_path.read_text(encoding="utf-8"))
        card = CharacterCard.model_validate(raw)
        return {"ok": True, "card": card.model_dump(mode="json")}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "card": None}


@router.put("/assistant/workspace/character-card", response_model=CharacterCard)
def put_workspace_character_card(card: CharacterCard) -> CharacterCard:
    """
    保存工作区角色卡草稿

    写入 data/ai_workspace/character_card.json，供助手工具 workspace_write_file 与前端共用同一暂存位置。
    """
    return save_workspace_character_card(card)


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
    更新AI助手设置：请求体中未出现的字段保留原值（含 prompt）。
    
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
    role: MainChatRole = "assistant"
    content: str = ""


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
    chat.messages.append(ChatMessage(role=req.role, content=req.content))
    return _save_assistant_chat_by_scope(scope, chatId, chat)


@router.post("/assistant/reset")
def reset_assistant(
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    """
    重置AI助手聊天
    
    清空聊天记录，如果scope不是workspace则同时清空AI工作空间。
    
    Args:
        chatId: 聊天会话ID（可选）
        scope: 作用域（可选）
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    _clear_assistant_chat_by_scope(scope, chatId)
    if scope != "workspace":
        clear_ai_workspace()
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


@router.post("/assistant/stream")
async def stream_assistant(req: AssistantStreamRequest) -> StreamingResponse:
    """
    流式 AI 助手对话。

    支持工具调用、多轮对话、推理内容等；作用域可为 workspace 或 chat。
    长期记忆写入与破坏性工具是否可用仅由请求体中的 allowWriteMemory、
    allowDestructiveTools 决定（工作区作用域下不会开启记忆写入）。

    Args:
        req: 流式请求对象

    Returns:
        StreamingResponse: SSE 流式响应
    """
    settings = load_settings()
    assistant_settings = load_assistant_settings()
    scope = req.scope
    chat_id = None if scope == "workspace" else req.chatId
    chat = _resolve_assistant_chat_by_scope(scope, chat_id)

    model = req.model or assistant_settings.model or settings.llm.defaultModel
    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    temperature = req.temperature if req.temperature is not None else assistant_settings.temperature
    if model == "deepseek-reasoner" or thinking_enabled:
        temperature = None

    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    preset_id = assistant_settings.presetId
    found_preset = None
    if preset_id and settings.apiPresets:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey
    # 当未关联预设或未找到时，根据当前模型在预设列表中查找所属预设，避免错误使用顺位第一的预设
    if not found_preset and model and settings.apiPresets:
        found_preset = next(
            (p for p in settings.apiPresets if p.models and model in p.models),
            None,
        )
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey
    if not base_url and settings.apiPresets:
        first_preset = settings.apiPresets[0]
        base_url = first_preset.baseUrl
        api_key = first_preset.apiKey

    existing_messages = chat.messages or []
    
    if req.appendUserMessage:
        new_user_msg = ChatMessage(role="user", content=req.userMessage)
        existing_messages.append(new_user_msg)
        chat.messages = existing_messages
        _save_assistant_chat_by_scope(scope, chat_id, chat)

    conversation = _assistant_messages_to_openai(list(existing_messages))
    _compact_tool_result_contents_for_llm(conversation)
    context_size = getattr(assistant_settings, "context_size", None)
    if context_size and context_size >= 1:
        conversation = trim_assistant_openai_messages_to_context(conversation, context_size, None)

    llm_msgs: list[dict[str, Any]] = []
    _ensure_system_prompt(llm_msgs, assistant_settings.prompt)
    participants_prompt = _build_chat_participants_prompt(chat_id)
    if participants_prompt:
        llm_msgs.append({"role": "system", "content": participants_prompt})
    llm_msgs.extend(conversation)

    if model == "deepseek-reasoner" or thinking_enabled:
        _clear_reasoning_content(llm_msgs)

    allow_write_memory = bool(req.allowWriteMemory) if req.allowWriteMemory is not None else False
    if scope == "workspace":
        allow_write_memory = False
    allow_destructive_tools = bool(req.allowDestructiveTools) if req.allowDestructiveTools is not None else False
    tool_ctx = AssistantToolContext(
        chat_id=chat_id,
        scope=scope,
        allow_write_memory=allow_write_memory,
        allow_destructive_tools=allow_destructive_tools,
        assistant_settings=assistant_settings,
    )
    tools = build_openai_tools_list(tool_ctx)
    extra_body = filter_reasoning_extra_body_for_upstream(model, reasoning_cfg["extra_body"])

    # 非流式：与全局设置 streamEnabled 一致，返回 JSON
    if not getattr(settings, "streamEnabled", True):
        current_messages = list(llm_msgs)
        max_turns = 8
        tool_traces: list[dict[str, Any]] = []
        wb_updates: list[dict[str, Any]] = []
        co_updates: list[dict[str, Any]] = []
        last_card: Any = None
        try:
            for _ in range(max_turns):
                resp = await chat_completions_message(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=current_messages,
                    temperature=temperature,
                    tools=tools,
                    extra_body=extra_body,
                )
                tool_calls_raw = resp.tool_calls
                tool_calls_for_llm: list[dict[str, Any]] | None = None
                if tool_calls_raw is not None:
                    tool_calls_for_llm = _normalize_tool_calls_ids(tool_calls_raw)
                llm_assistant_msg: dict[str, Any] = {
                    "role": resp.role or "assistant",
                    "content": resp.content or "",
                }
                if resp.reasoning_content:
                    llm_assistant_msg["reasoning_content"] = resp.reasoning_content
                if tool_calls_for_llm is not None:
                    llm_assistant_msg["tool_calls"] = tool_calls_for_llm
                current_messages.append(llm_assistant_msg)

                if not tool_calls_raw:
                    final_content = resp.content or ""
                    final_reasoning_content = resp.reasoning_content
                    assistant_msg_obj = ChatMessage(
                        role=resp.role or "assistant",
                        content=final_content,
                        reasoningContent=final_reasoning_content or None,
                    )
                    chat_to_save = _resolve_assistant_chat_by_scope(scope, chat_id)
                    chat_to_save.messages.append(assistant_msg_obj)
                    _save_assistant_chat_by_scope(scope, chat_id, chat_to_save)
                    return JSONResponse({
                        "ok": True,
                        "stream": False,
                        "content": final_content,
                        "messageId": assistant_msg_obj.id,
                        "toolTraces": tool_traces,
                        "card": last_card,
                        "worldbookUpdated": wb_updates,
                        "chatOverridesUpdated": co_updates,
                    })

                assistant_with_tools = ChatMessage(
                    role=resp.role or "assistant",
                    content=resp.content or "",
                    tool_calls=list(tool_calls_for_llm or []),
                    reasoningContent=resp.reasoning_content or None,
                )
                chat_turn = _resolve_assistant_chat_by_scope(scope, chat_id)
                chat_turn.messages.append(assistant_with_tools)
                _save_assistant_chat_by_scope(scope, chat_id, chat_turn)

                tool_idx = 0
                for tool_call in tool_calls_for_llm or []:
                    fn = (tool_call.get("function") or {}).get("name")
                    raw_args = (tool_call.get("function") or {}).get("arguments") or "{}"
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                    tool_name = str(fn)
                    outcome = execute_tool(tool_name, args, tool_ctx)
                    result = outcome.result
                    if outcome.card:
                        last_card = outcome.card
                    if outcome.worldbook_updated:
                        wb_updates.append(outcome.worldbook_updated)
                    if outcome.chat_overrides_updated:
                        co_updates.append(outcome.chat_overrides_updated)
                    tid = str(tool_call.get("id") or "").strip()
                    tool_msg = ChatMessage(
                        role="tool",
                        tool_call_id=tid,
                        content=json.dumps(result, ensure_ascii=False),
                    )
                    trace_chat = _resolve_assistant_chat_by_scope(scope, chat_id)
                    trace_chat.messages.append(tool_msg)
                    _save_assistant_chat_by_scope(scope, chat_id, trace_chat)
                    tr = _tool_record_payload(tool_name, tool_idx, result, args)
                    tool_idx += 1
                    tool_traces.append({"record": tr, "messageId": tool_msg.id, "content": tool_msg.content})
                    tool_result_msg = {
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    current_messages.append(tool_result_msg)

            return JSONResponse({"ok": False, "error": "tool call loop limit exceeded"}, status_code=500)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    async def event_iter() -> AsyncIterator[str]:
        """
        流式事件迭代器
        
        使用 stream_chat_completions 逐块推送 reasoning 与 content，实现打字机效果。
        支持多轮工具调用，最多8轮。如果检测到character_card.json，会发送card事件。
        
        Yields:
            str: SSE格式的事件字符串
        """
        current_messages = list(llm_msgs)
        max_turns = 8
        tool_idx_stream = 0

        for _ in range(max_turns):
            final_content = ""
            final_reasoning_content = ""
            llm_assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "",
            }
            tool_calls_from_stream: list[dict[str, Any]] | None = None
            normalized_stream: list[dict[str, Any]] = []

            try:
                async for chunk in stream_chat_completions(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=current_messages,
                    temperature=temperature,
                    tools=tools,
                    extra_body=extra_body,
                ):
                    if chunk.kind == "reasoning":
                        final_reasoning_content += chunk.text
                        yield _sse("reasoning", {"text": chunk.text})
                    elif chunk.kind == "content":
                        final_content += chunk.text
                        yield _sse("delta", {"text": chunk.text})
                    elif chunk.kind == "finish":
                        tool_calls_from_stream = chunk.tool_calls
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})
                return

            if final_reasoning_content:
                llm_assistant_msg["reasoning_content"] = final_reasoning_content
            llm_assistant_msg["content"] = final_content
            if tool_calls_from_stream:
                normalized_stream = _normalize_tool_calls_ids(tool_calls_from_stream)
                llm_assistant_msg["tool_calls"] = normalized_stream
            current_messages.append(llm_assistant_msg)

            if not tool_calls_from_stream:
                assistant_msg_obj = ChatMessage(
                    role="assistant",
                    content=final_content,
                    reasoningContent=final_reasoning_content or None,
                )
                chat_to_save = _resolve_assistant_chat_by_scope(scope, chat_id)
                chat_to_save.messages.append(assistant_msg_obj)
                _save_assistant_chat_by_scope(scope, chat_id, chat_to_save)
                yield _sse("done", {"ok": True, "messageId": assistant_msg_obj.id})
                return

            assistant_with_tools = ChatMessage(
                role="assistant",
                content=final_content or "",
                tool_calls=list(normalized_stream),
                reasoningContent=final_reasoning_content or None,
            )
            chat_turn = _resolve_assistant_chat_by_scope(scope, chat_id)
            chat_turn.messages.append(assistant_with_tools)
            _save_assistant_chat_by_scope(scope, chat_id, chat_turn)

            for tool_call in normalized_stream:
                fn = (tool_call.get("function") or {}).get("name")
                raw_args = (tool_call.get("function") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                tool_name = str(fn)
                outcome = execute_tool(tool_name, args, tool_ctx)
                result = outcome.result
                tid = str(tool_call.get("id") or "").strip()
                tool_msg = ChatMessage(
                    role="tool",
                    tool_call_id=tid,
                    content=json.dumps(result, ensure_ascii=False),
                )
                trace_chat = _resolve_assistant_chat_by_scope(scope, chat_id)
                trace_chat.messages.append(tool_msg)
                _save_assistant_chat_by_scope(scope, chat_id, trace_chat)
                tr = _tool_record_payload(tool_name, tool_idx_stream, result, args)
                tool_idx_stream += 1
                yield _sse(
                    "tool_trace",
                    {"record": tr, "messageId": tool_msg.id, "content": tool_msg.content},
                )
                if outcome.card:
                    yield _sse("card", {"card": outcome.card})
                if outcome.chat_memory_updated:
                    yield _sse("chat_memory_updated", {"chat": outcome.chat_memory_updated})
                if outcome.worldbook_updated:
                    yield _sse("worldbook_updated", outcome.worldbook_updated)
                if outcome.chat_overrides_updated:
                    yield _sse("chat_overrides_updated", outcome.chat_overrides_updated)
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": json.dumps(result, ensure_ascii=False),
                }
                current_messages.append(tool_result_msg)

        yield _sse("error", {"message": "tool call loop limit exceeded"})

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
