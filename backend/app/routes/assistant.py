from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.openai_compat import chat_completions_message
from app.schemas import (
    AssistantChat,
    AssistantSettings,
    CharacterCard,
    ChatMessage,
    UpdateMessageRequest,
)
from app.storage import (
    ai_workspace_dir,
    clear_ai_workspace,
    clear_assistant_chat,
    load_assistant_chat,
    load_assistant_settings,
    load_settings,
    save_assistant_chat,
    save_assistant_settings,
)


router = APIRouter(tags=["assistant"])


class AssistantStreamRequest(BaseModel):
    userMessage: str
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    appendUserMessage: bool | None = True


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


def _build_tools() -> list[dict[str, Any]]:
    return [
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


def _run_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
def get_assistant_chat() -> AssistantChat:
    return load_assistant_chat()


@router.post("/assistant/reset")
def reset_assistant() -> dict:
    clear_assistant_chat()
    clear_ai_workspace()
    return {"ok": True}


@router.put("/assistant/chat/messages/{message_id}")
def update_assistant_message(message_id: str, req: UpdateMessageRequest) -> AssistantChat:
    chat = load_assistant_chat()
    for m in chat.messages:
        if m.id == message_id:
            m.role = req.role
            m.content = req.content
            save_assistant_chat(chat)
            return chat
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="message not found")


@router.delete("/assistant/chat/messages/{message_id}")
def delete_assistant_message(message_id: str) -> AssistantChat:
    chat = load_assistant_chat()
    new_msgs = [m for m in chat.messages if m.id != message_id]
    chat.messages = new_msgs
    save_assistant_chat(chat)
    return chat


@router.post("/assistant/stream")
async def stream_assistant(req: AssistantStreamRequest) -> StreamingResponse:
    settings = load_settings()
    assistant_settings = load_assistant_settings()
    chat = load_assistant_chat()

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
        save_assistant_chat(chat)

    # 准备发送给 LLM 的消息列表
    llm_msgs: list[dict[str, Any]] = []
    _ensure_system_prompt(llm_msgs, assistant_settings.prompt)
    
    for m in existing_messages:
        msg_dict = {"role": m.role, "content": m.content}
        # 兼容 reasoning_content (如果存储了)
        if hasattr(m, "extra") and isinstance(m.extra, dict) and "reasoning_content" in m.extra:
             msg_dict["reasoning_content"] = m.extra["reasoning_content"]
        llm_msgs.append(msg_dict)

    if model == "deepseek-reasoner":
        _clear_reasoning_content(llm_msgs)

    tools = _build_tools()
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
                
                chat_to_save = load_assistant_chat()
                chat_to_save.messages.append(assistant_msg_obj)
                save_assistant_chat(chat_to_save)
                
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
                
                result, card = _run_tool(str(fn), args)
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
