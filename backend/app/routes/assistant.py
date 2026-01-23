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
    - PUT /assistant/chat/messages/{message_id}: 更新助手消息
    - DELETE /assistant/chat/messages/{message_id}: 删除助手消息

主要函数：
    - stream_assistant: 流式AI助手对话
    - get_assistant_settings: 获取助手设置
    - put_assistant_settings: 更新助手设置
    - get_assistant_chat: 获取助手聊天记录
    - reset_assistant: 重置助手聊天
    - get_workspace_character_card: 获取工作空间角色卡
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
import re
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.openai_compat import chat_completions_message
from app.schemas import (
    AssistantChat,
    AssistantSettings,
    Chat,
    CharacterCard,
    ChatMessage,
    UpdateMessageRequest,
)
from app.storage import (
    ai_workspace_dir,
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
    save_chat_memory,
    save_assistant_settings,
)


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


def _resolve_ai_path(path_str: str) -> Path:
    """
    解析AI工作空间内的相对路径
    
    确保路径在ai_workspace目录下，不允许绝对路径或越界访问。
    
    Args:
        path_str: 相对路径字符串
    
    Returns:
        Path: 解析后的完整路径
    
    Raises:
        ValueError: 路径为空、为绝对路径或越界时抛出
    """
    if not path_str or path_str.strip() == "":
        raise ValueError("path is required")
    raw = Path(path_str)
    if raw.is_absolute():
        raise ValueError("absolute path is not allowed")
    base = ai_workspace_dir().resolve()
    target = (base / raw).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("path must be under ai_workspace") from exc
    return target


def _tool_read_file(args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：读取文件
    
    Args:
        args: 工具参数，包含path
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    path_str = str(args.get("path") or "")
    target = _resolve_ai_path(path_str)
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found", "path": path_str}
    content = target.read_text(encoding="utf-8")
    return {"ok": True, "path": path_str, "content": content}


def _tool_create_file(args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：创建文件
    
    文件已存在时失败。
    
    Args:
        args: 工具参数，包含path和content
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    target = _resolve_ai_path(path_str)
    if target.exists():
        return {"ok": False, "error": "file already exists", "path": path_str}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path_str}


def _tool_write_file(args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：写入文件
    
    文件存在则覆盖。
    
    Args:
        args: 工具参数，包含path和content
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    target = _resolve_ai_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path_str}


def _tool_delete_file(args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：删除文件
    
    Args:
        args: 工具参数，包含path
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    path_str = str(args.get("path") or "")
    target = _resolve_ai_path(path_str)
    if target.exists() and target.is_file():
        target.unlink(missing_ok=True)
    return {"ok": True, "path": path_str}


def _load_chat_context(chat_id: str) -> Chat | None:
    """
    加载聊天上下文
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        Chat | None: 聊天对象，不存在返回None
    """
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        return None


def _tool_read_chat_json(chat_id: str) -> dict[str, Any]:
    """
    工具：读取聊天JSON
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    return {"ok": True, "chat": chat.model_dump(mode="json")}


def _tool_read_chat_memory(chat_id: str) -> dict[str, Any]:
    """
    工具：读取聊天长期记忆
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    try:
        memory = load_chat_memory(chat.characterId, chat.id)
    except FileNotFoundError:
        return {"ok": False, "error": "chat memory not found", "chatId": chat_id}
    return {"ok": True, "chatId": chat_id, "content": memory}


def _tool_write_chat_memory(chat_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：写入聊天长期记忆
    
    Args:
        chat_id: 聊天会话ID
        args: 工具参数，包含content
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    content = str(args.get("content") or "")
    save_chat_memory(chat.characterId, chat.id, content)
    return {"ok": True, "chatId": chat_id}


def _tool_read_character_card(chat_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    工具：读取角色卡片
    
    只能读取当前聊天参与的角色。
    
    Args:
        chat_id: 聊天会话ID
        args: 工具参数，包含characterId
    
    Returns:
        dict[str, Any]: 工具执行结果
    """
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    target_id = str(args.get("characterId") or "")
    participant_ids = set(chat.memberIds or [])
    if not participant_ids:
        participant_ids.add(chat.characterId)
    if target_id not in participant_ids:
        return {"ok": False, "error": "character not in chat", "characterId": target_id}
    try:
        card = load_character(target_id)
    except FileNotFoundError:
        return {"ok": False, "error": "character not found", "characterId": target_id}
    return {"ok": True, "character": card.model_dump(mode="json")}


def _tool_list_participants(chat_id: str) -> dict[str, Any]:
    """
    工具：列出聊天参与者
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        dict[str, Any]: 工具执行结果，包含参与者列表
    """
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    participant_ids = chat.memberIds if chat.isGroup else [chat.characterId]
    participants = []
    for cid in participant_ids:
        try:
            card = load_character(cid)
            participants.append({"id": cid, "name": card.name, "avatar": card.avatar})
        except FileNotFoundError:
            participants.append({"id": cid, "name": "", "avatar": ""})
    return {"ok": True, "participants": participants}


def _try_parse_character_card(path_str: str, content: str | None) -> dict[str, Any] | None:
    """
    尝试解析角色卡片
    
    如果路径是character_card.json，尝试从内容或文件中解析角色卡片。
    
    Args:
        path_str: 文件路径
        content: 文件内容（可选）
    
    Returns:
        dict[str, Any] | None: 解析后的角色卡片字典，失败返回None
    """
    if Path(path_str).name != "character_card.json":
        return None
    raw: Any
    try:
        raw = json.loads(content) if content is not None else None
    except Exception:
        raw = None
    if raw is None:
        try:
            target = _resolve_ai_path(path_str)
            raw = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None
    try:
        card = CharacterCard.model_validate(raw)
    except Exception:
        return None
    return card.model_dump(mode="json")


def _build_tools(chat_id: str | None, allow_write_memory: bool) -> list[dict[str, Any]]:
    """
    构建工具列表
    
    根据chat_id和allow_write_memory决定包含哪些工具。
    
    Args:
        chat_id: 聊天会话ID（可选）
        allow_write_memory: 是否允许写入长期记忆
    
    Returns:
        list[dict[str, Any]]: 工具定义列表
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取 data/ai_workspace/ 下的文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对路径，如 character_card.json"}
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "新建文件并写入内容（文件已存在时失败）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对路径，如 character_card.json"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "写入文件内容（存在则覆盖）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对路径，如 character_card.json"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "删除 data/ai_workspace/ 下的文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对路径，如 character_card.json"}
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
    ]
    if chat_id:
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "read_chat_json",
                        "description": "读取当前聊天 chat.json 的内容",
                        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "read_chat_memory",
                        "description": "读取当前聊天 chat_memory.json 的内容",
                        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "read_character_card",
                        "description": "读取当前聊天参与角色的角色卡",
                        "parameters": {
                            "type": "object",
                            "properties": {"characterId": {"type": "string"}},
                            "required": ["characterId"],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "list_participants",
                        "description": "列出当前聊天参与角色及其ID",
                        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                },
            ]
        )
        if allow_write_memory:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "write_chat_memory",
                        "description": "写入当前聊天 chat_memory.json 的内容",
                        "parameters": {
                            "type": "object",
                            "properties": {"content": {"type": "string"}},
                            "required": ["content"],
                            "additionalProperties": False,
                        },
                    },
                }
            )
    return tools


def _run_tool(
    name: str,
    args: dict[str, Any],
    chat_id: str | None,
    allow_write_memory: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    执行工具调用
    
    Args:
        name: 工具名称
        args: 工具参数
        chat_id: 聊天会话ID（可选）
        allow_write_memory: 是否允许写入长期记忆
    
    Returns:
        tuple[dict[str, Any], dict[str, Any] | None]: (工具执行结果, 解析出的角色卡片)
    """
    content_for_card: str | None = None
    path_str = str(args.get("path") or "")
    try:
        if name == "read_file":
            return _tool_read_file(args), None
        if name == "create_file":
            content_for_card = str(args.get("content") or "")
            result = _tool_create_file(args)
        elif name == "write_file":
            content_for_card = str(args.get("content") or "")
            result = _tool_write_file(args)
        elif name == "delete_file":
            result = _tool_delete_file(args)
        elif name == "read_chat_json" and chat_id:
            return _tool_read_chat_json(chat_id), None
        elif name == "read_chat_memory" and chat_id:
            return _tool_read_chat_memory(chat_id), None
        elif name == "write_chat_memory" and chat_id and allow_write_memory:
            return _tool_write_chat_memory(chat_id, args), None
        elif name == "read_character_card" and chat_id:
            return _tool_read_character_card(chat_id, args), None
        elif name == "list_participants" and chat_id:
            return _tool_list_participants(chat_id), None
        else:
            return {"ok": False, "error": "unknown tool"}, None
        card = _try_parse_character_card(path_str, content_for_card)
        return result, card
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": path_str}, None


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


def _explicit_memory_write_requested(text: str) -> bool:
    """
    检查用户消息中是否明确要求写入长期记忆
    
    Args:
        text: 用户消息文本
    
    Returns:
        bool: 如果包含写入记忆的关键词返回True
    """
    if not text:
        return False
    patterns = [
        r"写入.*记忆",
        r"更新.*记忆",
        r"保存.*记忆",
        r"记录.*记忆",
        r"写.*长期记忆",
        r"保存.*长期记忆",
    ]
    return any(re.search(p, text) for p in patterns)


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


@router.get("/assistant/settings", response_model=AssistantSettings)
def get_assistant_settings() -> AssistantSettings:
    """
    获取AI助手设置
    
    Returns:
        AssistantSettings: 助手设置对象
    """
    return load_assistant_settings()


@router.put("/assistant/settings", response_model=AssistantSettings)
def put_assistant_settings(settings: AssistantSettings) -> AssistantSettings:
    """
    更新AI助手设置
    
    Args:
        settings: 助手设置对象
    
    Returns:
        AssistantSettings: 保存后的设置对象
    """
    return save_assistant_settings(settings)


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
    流式AI助手对话
    
    支持工具调用、多轮对话、推理内容等。支持workspace和chat两种作用域。
    自动检测用户消息中是否包含写入记忆的请求。
    
    Args:
        req: 流式请求对象
    
    Returns:
        StreamingResponse: SSE流式响应
    """
    settings = load_settings()
    assistant_settings = load_assistant_settings()
    scope = req.scope
    chat_id = None if scope == "workspace" else req.chatId
    chat = _resolve_assistant_chat_by_scope(scope, chat_id)

    model = req.model or assistant_settings.model or settings.llm.defaultModel
    temperature = req.temperature if req.temperature is not None else assistant_settings.temperature
    if model == "deepseek-reasoner":
        temperature = None

    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    preset_id = assistant_settings.presetId
    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey
    if not base_url and settings.apiPresets:
        first_preset = settings.apiPresets[0]
        base_url = first_preset.baseUrl
        api_key = first_preset.apiKey

    messages_for_llm: list[dict[str, Any]] = []
    
    existing_messages = chat.messages or []
    
    if req.appendUserMessage:
        new_user_msg = ChatMessage(role="user", content=req.userMessage)
        existing_messages.append(new_user_msg)
        chat.messages = existing_messages
        _save_assistant_chat_by_scope(scope, chat_id, chat)

    llm_msgs: list[dict[str, Any]] = []
    _ensure_system_prompt(llm_msgs, assistant_settings.prompt)
    participants_prompt = _build_chat_participants_prompt(chat_id)
    if participants_prompt:
        llm_msgs.append({"role": "system", "content": participants_prompt})
    
    for m in existing_messages:
        if getattr(m, "toolTrace", False):
            continue
        msg_dict = {"role": m.role, "content": m.content}
        if hasattr(m, "extra") and isinstance(m.extra, dict) and "reasoning_content" in m.extra:
             msg_dict["reasoning_content"] = m.extra["reasoning_content"]
        llm_msgs.append(msg_dict)

    if model == "deepseek-reasoner":
        _clear_reasoning_content(llm_msgs)

    allow_write_memory = req.allowWriteMemory
    if allow_write_memory is None and scope != "workspace":
        allow_write_memory = _explicit_memory_write_requested(req.userMessage)
    if scope == "workspace":
        allow_write_memory = False
    tools = _build_tools(chat_id, bool(allow_write_memory))
    extra_body = {"thinking": {"type": "enabled"}} if model == "deepseek-reasoner" else None

    async def event_iter() -> AsyncIterator[str]:
        """
        流式事件迭代器
        
        支持多轮工具调用，最多8轮。如果检测到character_card.json，会发送card事件。
        
        Yields:
            str: SSE格式的事件字符串
        """
        current_messages = list(llm_msgs)
        max_turns = 8
        final_content = ""
        final_reasoning_content: str | None = None
        
        for _ in range(max_turns):
            try:
                resp = await chat_completions_message(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=current_messages,
                    temperature=temperature,
                    tools=tools,
                    extra_body=extra_body,
                )
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})
                return

            llm_assistant_msg: dict[str, Any] = {
                "role": resp.role or "assistant",
                "content": resp.content or "",
            }
            if resp.reasoning_content:
                llm_assistant_msg["reasoning_content"] = resp.reasoning_content
            if resp.tool_calls is not None:
                llm_assistant_msg["tool_calls"] = resp.tool_calls
            current_messages.append(llm_assistant_msg)

            if not resp.tool_calls:
                final_content = resp.content or ""
                final_reasoning_content = resp.reasoning_content
                
                assistant_msg_obj = ChatMessage(
                    role=resp.role or "assistant",
                    content=final_content,
                )
                if final_reasoning_content:
                    assistant_msg_obj.model_config["extra"] = {"reasoning_content": final_reasoning_content}
                
                chat_to_save = _resolve_assistant_chat_by_scope(scope, chat_id)
                chat_to_save.messages.append(assistant_msg_obj)
                _save_assistant_chat_by_scope(scope, chat_id, chat_to_save)
                
                if final_content:
                    yield _sse("delta", {"text": final_content})
                yield _sse("done", {"ok": True, "messageId": assistant_msg_obj.id})
                return

            for tool_call in resp.tool_calls or []:
                fn = (tool_call.get("function") or {}).get("name")
                raw_args = (tool_call.get("function") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                
                tool_name = str(fn)
                result, card = _run_tool(tool_name, args, chat_id, bool(allow_write_memory))
                trace_content = f"工具调用：{tool_name}"
                if args:
                    trace_content += f"\n参数：{json.dumps(args, ensure_ascii=False)}"
                trace_msg = ChatMessage(role="system", content=trace_content, toolTrace=True)
                trace_chat = _resolve_assistant_chat_by_scope(scope, chat_id)
                trace_chat.messages.append(trace_msg)
                _save_assistant_chat_by_scope(scope, chat_id, trace_chat)
                yield _sse("tool_trace", {"content": trace_content, "messageId": trace_msg.id})
                if card:
                    yield _sse("card", {"card": card})
                
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
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
