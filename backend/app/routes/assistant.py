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
    userMessage: str
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    appendUserMessage: bool | None = True
    chatId: str | None = None
    allowWriteMemory: bool | None = None
    scope: str | None = None


def _sse(event: str, data_obj: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


def _resolve_ai_path(path_str: str) -> Path:
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
    path_str = str(args.get("path") or "")
    target = _resolve_ai_path(path_str)
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found", "path": path_str}
    content = target.read_text(encoding="utf-8")
    return {"ok": True, "path": path_str, "content": content}


def _tool_create_file(args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    target = _resolve_ai_path(path_str)
    if target.exists():
        return {"ok": False, "error": "file already exists", "path": path_str}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path_str}


def _tool_write_file(args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    target = _resolve_ai_path(path_str)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path_str}


def _tool_delete_file(args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    target = _resolve_ai_path(path_str)
    if target.exists() and target.is_file():
        target.unlink(missing_ok=True)
    return {"ok": True, "path": path_str}


def _load_chat_context(chat_id: str) -> Chat | None:
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        return None


def _tool_read_chat_json(chat_id: str) -> dict[str, Any]:
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    return {"ok": True, "chat": chat.model_dump(mode="json")}


def _tool_read_chat_memory(chat_id: str) -> dict[str, Any]:
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    try:
        memory = load_chat_memory(chat.characterId, chat.id)
    except FileNotFoundError:
        return {"ok": False, "error": "chat memory not found", "chatId": chat_id}
    return {"ok": True, "chatId": chat_id, "content": memory}


def _tool_write_chat_memory(chat_id: str, args: dict[str, Any]) -> dict[str, Any]:
    chat = _load_chat_context(chat_id)
    if chat is None:
        return {"ok": False, "error": "chat not found", "chatId": chat_id}
    content = str(args.get("content") or "")
    save_chat_memory(chat.characterId, chat.id, content)
    return {"ok": True, "chatId": chat_id}


def _tool_read_character_card(chat_id: str, args: dict[str, Any]) -> dict[str, Any]:
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
    for msg in messages:
        if "reasoning_content" in msg:
            msg.pop("reasoning_content", None)


def _ensure_system_prompt(messages: list[dict[str, Any]], prompt: str) -> None:
    if not prompt or not prompt.strip():
        return
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = prompt
        return
    messages.insert(0, {"role": "system", "content": prompt})


def _resolve_assistant_chat(chat_id: str | None) -> AssistantChat:
    if chat_id:
        try:
            return load_assistant_chat_for_chat(chat_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="chat not found")
    return load_assistant_chat()


def _save_assistant_chat(chat_id: str | None, chat: AssistantChat) -> AssistantChat:
    if chat_id:
        return save_assistant_chat_for_chat(chat_id, chat)
    return save_assistant_chat(chat)


def _clear_assistant_chat(chat_id: str | None) -> None:
    if chat_id:
        try:
            clear_assistant_chat_for_chat(chat_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="chat not found")
    else:
        clear_assistant_chat()


def _resolve_assistant_chat_by_scope(scope: str | None, chat_id: str | None) -> AssistantChat:
    if scope == "workspace":
        return load_assistant_workspace_chat()
    return _resolve_assistant_chat(chat_id)


def _save_assistant_chat_by_scope(scope: str | None, chat_id: str | None, chat: AssistantChat) -> AssistantChat:
    if scope == "workspace":
        return save_assistant_workspace_chat(chat)
    return _save_assistant_chat(chat_id, chat)


def _clear_assistant_chat_by_scope(scope: str | None, chat_id: str | None) -> None:
    if scope == "workspace":
        clear_assistant_workspace_chat()
    else:
        _clear_assistant_chat(chat_id)


def _explicit_memory_write_requested(text: str) -> bool:
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
    """读取 ai_workspace/character_card.json 的内容（如存在）"""
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
    return load_assistant_settings()


@router.put("/assistant/settings", response_model=AssistantSettings)
def put_assistant_settings(settings: AssistantSettings) -> AssistantSettings:
    return save_assistant_settings(settings)


@router.get("/assistant/chat", response_model=AssistantChat)
def get_assistant_chat(
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
    return _resolve_assistant_chat_by_scope(scope, chatId)


@router.post("/assistant/reset")
def reset_assistant(
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict:
    _clear_assistant_chat_by_scope(scope, chatId)
    if scope != "workspace":
        clear_ai_workspace()
    return {"ok": True}


@router.post("/assistant/workspace/chat/delete")
def delete_workspace_chat() -> dict:
    delete_assistant_workspace_chat()
    return {"ok": True}


@router.put("/assistant/chat/messages/{message_id}")
def update_assistant_message(
    message_id: str,
    req: UpdateMessageRequest,
    chatId: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> AssistantChat:
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
    chat = _resolve_assistant_chat_by_scope(scope, chatId)
    new_msgs = [m for m in chat.messages if m.id != message_id]
    chat.messages = new_msgs
    _save_assistant_chat_by_scope(scope, chatId, chat)
    return chat


@router.post("/assistant/stream")
async def stream_assistant(req: AssistantStreamRequest) -> StreamingResponse:
    settings = load_settings()
    assistant_settings = load_assistant_settings()
    scope = req.scope
    chat_id = None if scope == "workspace" else req.chatId
    chat = _resolve_assistant_chat_by_scope(scope, chat_id)

    model = req.model or assistant_settings.model or settings.llm.defaultModel
    temperature = req.temperature if req.temperature is not None else assistant_settings.temperature
    if model == "deepseek-reasoner":
        temperature = None

    # 确定 API 配置 (presetId > 第一个预设 > Global)
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    preset_id = assistant_settings.presetId
    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey
    # 如果没有配置 presetId，且全局 baseUrl 为空，尝试使用第一个可用预设
    if not base_url and settings.apiPresets:
        first_preset = settings.apiPresets[0]
        base_url = first_preset.baseUrl
        api_key = first_preset.apiKey

    messages_for_llm: list[dict[str, Any]] = []
    
    # 构建基础历史
    existing_messages = chat.messages or []
    
    if req.appendUserMessage:
        new_user_msg = ChatMessage(role="user", content=req.userMessage)
        existing_messages.append(new_user_msg)
        chat.messages = existing_messages
        _save_assistant_chat_by_scope(scope, chat_id, chat)

    # 准备发送给 LLM 的消息列表
    llm_msgs: list[dict[str, Any]] = []
    _ensure_system_prompt(llm_msgs, assistant_settings.prompt)
    participants_prompt = _build_chat_participants_prompt(chat_id)
    if participants_prompt:
        llm_msgs.append({"role": "system", "content": participants_prompt})
    
    for m in existing_messages:
        if getattr(m, "toolTrace", False):
            continue
        msg_dict = {"role": m.role, "content": m.content}
        # 兼容 reasoning_content (如果存储了)
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

            # 准备下一轮的 LLM 消息
            llm_assistant_msg: dict[str, Any] = {
                "role": resp.role or "assistant",
                "content": resp.content or "",
            }
            if resp.reasoning_content:
                llm_assistant_msg["reasoning_content"] = resp.reasoning_content
            if resp.tool_calls is not None:
                llm_assistant_msg["tool_calls"] = resp.tool_calls
            current_messages.append(llm_assistant_msg)

            # 如果没有工具调用，说明是最终回复
            if not resp.tool_calls:
                final_content = resp.content or ""
                final_reasoning_content = resp.reasoning_content
                
                # 只在最终回复时保存助手消息
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

            # 有工具调用，执行工具
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
