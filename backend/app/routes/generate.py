"""
消息生成路由模块

提供AI消息生成的API端点，支持单聊和群聊两种模式，支持流式和非流式输出。

主要功能：
    - POST /generate/stream: 单聊流式生成（支持纯AI模式）
    - POST /generate/group: 群聊生成（指定角色回复）
    - POST /generate/interject: 群聊单次插话（让指定角色额外回复）

主要函数：
    - generate_stream: 单聊流式生成
    - generate_group_response: 群聊生成
    - generate_single_interject: 群聊单次插话

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入llm/openai_compat.py、schemas.py的生成相关模型和storage.py
    - 依赖：依赖llm/openai_compat.py、schemas.py和storage.py
    - 位置：路由层，处理消息生成相关的HTTP请求
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.llm.openai_compat import chat_completions, chat_completions_message, stream_chat_completions
from app.placeholders import replace_placeholders_in_text
from app.regex_compat import compile_user_regex
from app.schemas import (
    build_reasoning_request_config,
    ChatMessage,
    DraftHelpConversationMessage,
    DraftHelpRequest,
    GenerateStreamRequest,
    GroupGenerateRequest,
    SingleInterjectRequest,
)
from app.storage import load_character, load_chat, load_chat_image_bytes, load_settings, save_chat, save_settings
from app.storage import list_worldbooks
from app.tokenizer_service import count_tokens, count_tokens_for_messages, trim_messages_to_context


router = APIRouter(tags=["generate"])


def _now_iso() -> str:
    """
    获取当前时间的ISO格式字符串
    
    Returns:
        str: 当前时间的ISO格式字符串
    """
    return datetime.now().astimezone().isoformat()


def _resolve_pure_ai_mode(settings, chat, runtime) -> bool:
    """
    解析纯AI模式设置
    
    优先级：runtimeOverrides > chat.overrides > settings
    
    Args:
        settings: 全局设置对象
        chat: 聊天对象
        runtime: 运行时覆盖设置
    
    Returns:
        bool: 是否启用纯AI模式
    """
    if runtime is not None and getattr(runtime, "pureAiMode", None) is not None:
        return bool(runtime.pureAiMode)
    if chat is not None and getattr(chat, "overrides", None) is not None and getattr(chat.overrides, "pureAiMode", None) is not None:
        return bool(chat.overrides.pureAiMode)
    return bool(getattr(settings, "pureAiMode", False))


def _resolve_selected_persona(settings, chat, pure_ai_mode):
    """
    解析选中的用户Persona
    
    纯AI模式下不返回Persona。
    
    Args:
        settings: 全局设置对象
        chat: 聊天对象
        pure_ai_mode: 是否启用纯AI模式
    
    Returns:
        UserPersona | None: 选中的Persona对象，未找到或纯AI模式返回None
    """
    if pure_ai_mode:
        return None
    persona_id = getattr(chat, "userPersonaId", None) or getattr(settings, "selectedPersonaId", None)
    if not persona_id or not getattr(settings, "userPersonas", None):
        return None
    return next((p for p in settings.userPersonas if p.id == persona_id), None)


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


def _resolve_user_name_for_message(msg: ChatMessage, fallback_user_name: str) -> str:
    return getattr(msg, "senderName", None) or fallback_user_name or "用户"


def _build_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _message_to_openai_content(
    chat,
    msg: ChatMessage,
    *,
    image_fallback_mode: bool,
) -> str | list[dict[str, Any]]:
    text = msg.content or ""
    images = getattr(msg, "images", []) or []
    if not images:
        return text
    if image_fallback_mode:
        suffix = "\n".join("[image]" for _ in images)
        return f"{text}\n{suffix}".strip()
    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append({"type": "text", "text": text})
    for img in images:
        try:
            b = load_chat_image_bytes(chat, img)
            parts.append({
                "type": "image_url",
                "image_url": {"url": _build_data_url(b, img.mimeType or "image/png")},
            })
        except FileNotFoundError:
            parts.append({"type": "text", "text": "[image]"})
    if not parts:
        return ""
    return parts


def _resolve_char_name_for_history_message(
    msg: ChatMessage,
    *,
    default_char_name: str,
    character_name_cache: dict[str, str],
) -> str:
    char_id = getattr(msg, "characterId", None)
    if not char_id:
        return default_char_name
    if char_id in character_name_cache:
        return character_name_cache[char_id]
    try:
        c = load_character(char_id)
        character_name_cache[char_id] = c.name or "角色"
    except FileNotFoundError:
        character_name_cache[char_id] = default_char_name
    return character_name_cache[char_id]


def _apply_placeholder_rewrite_to_history(
    chat,
    *,
    default_char_name: str,
    fallback_user_name: str,
) -> bool:
    changed = False
    char_cache: dict[str, str] = {}
    for msg in chat.messages:
        user_name = _resolve_user_name_for_message(msg, fallback_user_name)
        char_name = _resolve_char_name_for_history_message(
            msg,
            default_char_name=default_char_name,
            character_name_cache=char_cache,
        )
        replaced = replace_placeholders_in_text(
            msg.content or "",
            char_name=char_name,
            user_name=user_name,
        )
        if replaced != msg.content:
            msg.content = replaced
            changed = True
    if changed:
        chat.updatedAt = _now_iso()
        save_chat(chat)
    return changed


def _slice_conversation_with_anchor(conversation: list[dict], context_start_message_id: str | None) -> list[dict]:
    if not context_start_message_id:
        return conversation
    start_idx = 0
    for i, m in enumerate(conversation):
        if m.get("_message_id") == context_start_message_id:
            start_idx = i
            break
    return conversation[start_idx:]


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    return str(content or "")


def collect_active_worldbooks(
    chat_id: str,
    ordered_ids: list[str] | None = None,
    global_exclusions: set[str] | None = None,
):
    global_exclusions = global_exclusions or set()
    all_books = list_worldbooks()
    active: list[Any] = []
    for b in all_books:
        if bool(getattr(b, "globalActive", False)):
            if b.id in global_exclusions:
                continue
            active.append(b)
        elif chat_id in (getattr(b, "sessionChatIds", []) or []):
            active.append(b)
    if not ordered_ids:
        return active
    by_id = {b.id: b for b in active}
    ordered: list[Any] = []
    for worldbook_id in ordered_ids:
        book = by_id.pop(worldbook_id, None)
        if book is not None:
            ordered.append(book)
    ordered.extend(by_id.values())
    return ordered


def _resolve_effective_scan_depth(raw: int | None, settings: Any) -> int:
    if raw is not None and int(raw) >= 1:
        return int(raw)
    g = getattr(settings, "worldBookEntryScanDepthDefault", None)
    if g is None:
        g = 2
    return max(0, int(g))


def _book_worldbook_runtime_settings(chat: Any, settings: Any) -> dict[str, tuple[int, int]]:
    m: dict[str, tuple[int, int]] = {}
    for a in getattr(chat.overrides, "worldBookAttachments", None) or []:
        wid = getattr(a, "worldBookId", None)
        if not wid:
            continue
        sd = getattr(a, "scanDepth", None)
        ins = int(getattr(a, "insertDepth", 5) or 5)
        m[wid] = (_resolve_effective_scan_depth(sd, settings), max(1, ins))
    return m


def _runtime_scan_insert_for_book(book_id: str, chat: Any, settings: Any) -> tuple[int, int]:
    m = _book_worldbook_runtime_settings(chat, settings)
    default_scan = _resolve_effective_scan_depth(None, settings)
    return m.get(book_id, (default_scan, 5))


def match_worldbook_entries(book, conversation: list[dict], effective_scan: int) -> list[Any]:
    entries = sorted(list(getattr(book, "entries", []) or []), key=lambda e: int(getattr(e, "orderIndex", 0)))
    matched: list[Any] = []
    for entry in entries:
        if not bool(getattr(entry, "enabled", True)):
            continue
        if effective_scan <= 0:
            matched.append(entry)
            continue
        n = int(effective_scan)
        if n < 0:
            continue
        scope = conversation[-n:] if n > 0 else []
        scan_text = "\n".join(_extract_text_content(m.get("content")) for m in scope)
        pattern = (getattr(entry, "regex", "") or "").strip()
        if not pattern:
            continue
        try:
            if compile_user_regex(pattern, re.MULTILINE).search(scan_text):
                matched.append(entry)
        except re.error:
            continue
    return matched


def build_worldbook_injections(book, entries: list[Any], conversation_len: int, insert_depth: int) -> list[dict[str, Any]]:
    insert_depth = int(insert_depth)
    chunk_parts: list[str] = []
    for entry in sorted(entries, key=lambda e: int(getattr(e, "orderIndex", 0))):
        content = str(getattr(entry, "content", "") or "").strip()
        if content:
            chunk_parts.append(content)
    if not chunk_parts:
        return []
    insert_index = max(0, conversation_len - insert_depth)
    return [{
        "insert_index": insert_index,
        "message": {"role": "system", "content": "\n\n".join(chunk_parts)},
    }]


def insert_injections_into_conversation(conversation: list[dict], injections: list[dict[str, Any]]) -> list[dict]:
    output = [dict(item) for item in conversation]
    if not injections:
        return output
    indexed = list(enumerate(injections))
    indexed.sort(key=lambda pair: (int(pair[1]["insert_index"]), pair[0]), reverse=True)
    for _, injection in indexed:
        idx = int(injection["insert_index"])
        idx = max(0, min(idx, len(output)))
        output.insert(idx, dict(injection["message"]))
    return output


def _resolve_char_name_for_draft_help(chat) -> str:
    if not getattr(chat, "isGroup", False):
        try:
            c = load_character(chat.characterId)
            return c.name or "角色"
        except FileNotFoundError:
            return "角色"
    for msg in reversed(chat.messages):
        if msg.role == "assistant" and getattr(msg, "characterId", None):
            try:
                c = load_character(msg.characterId)
                return c.name or "角色"
            except FileNotFoundError:
                continue
    try:
        c = load_character(chat.characterId)
        return c.name or "角色"
    except FileNotFoundError:
        return "角色"


def _build_recent_dialog_text(
    chat,
    *,
    fallback_user_name: str,
    default_char_name: str,
    pure_ai_mode: bool = False,
    limit: int | None = None,
) -> str:
    if limit is None or limit < 1:
        recent = chat.messages
    else:
        recent = chat.messages[-limit:] if len(chat.messages) > limit else chat.messages
    lines: list[str] = []
    char_cache: dict[str, str] = {}
    for m in recent:
        user_name = _resolve_user_name_for_message(m, fallback_user_name)
        char_name = _resolve_char_name_for_history_message(
            m,
            default_char_name=default_char_name,
            character_name_cache=char_cache,
        )
        rendered_content = replace_placeholders_in_text(
            m.content or "",
            char_name=char_name,
            user_name=user_name,
        )
        # 将单条消息压成一个逻辑块，避免消息内部空行被误判成新的对话轮次。
        rendered_content = " ".join(line.strip() for line in rendered_content.splitlines() if line.strip())
        if not rendered_content:
            continue
        if m.role == "user" or (pure_ai_mode and m.role == "system"):
            lines.append(f"[{user_name}]: {rendered_content}")
        elif m.role == "assistant":
            lines.append(f"[{char_name}]: {rendered_content}")
        else:
            lines.append(f"[system]: {rendered_content}")
    # 每条对话之间空一行，降低模型误判说话人的概率。
    return "\n\n".join(lines).strip()


def _build_draft_help_history_messages(
    source_messages: list[ChatMessage | DraftHelpConversationMessage],
    *,
    fallback_user_name: str,
    default_char_name: str,
    pure_ai_mode: bool = False,
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    char_cache: dict[str, str] = {}
    for m in source_messages:
        user_name = _resolve_user_name_for_message(m, fallback_user_name)
        char_name = _resolve_char_name_for_history_message(
            m,
            default_char_name=default_char_name,
            character_name_cache=char_cache,
        )
        rendered_content = replace_placeholders_in_text(
            m.content or "",
            char_name=char_name,
            user_name=user_name,
        )
        rendered_content = " ".join(line.strip() for line in rendered_content.splitlines() if line.strip())
        if not rendered_content:
            continue
        if m.role == "user" or (pure_ai_mode and m.role == "system"):
            history.append({"role": "user", "content": f"[{user_name}]: {rendered_content}", "_message_id": m.id})
        elif m.role == "assistant":
            history.append({"role": "assistant", "content": f"[{char_name}]: {rendered_content}", "_message_id": m.id})
        else:
            history.append({"role": "system", "content": f"[system]: {rendered_content}", "_message_id": m.id})
    return history


def _limit_conversation_by_message_count(conversation: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None or limit < 1:
        return list(conversation)
    if len(conversation) <= limit:
        return list(conversation)
    return list(conversation[-limit:])


def _render_draft_help_history_text(conversation: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        str(item.get("content", "")).strip()
        for item in conversation
        if str(item.get("content", "")).strip()
    ).strip()


def _resolve_draft_help_context_limit(settings, chat) -> int | None:
    chat_limit = getattr(getattr(chat.overrides, "draftHelp", None), "context_message_limit", None)
    if chat_limit is not None and chat_limit >= 1:
        return int(chat_limit)
    global_limit = getattr(getattr(settings, "draftHelpDefaults", None), "context_message_limit", None)
    if global_limit is not None and global_limit >= 1:
        return int(global_limit)
    return None


def _build_draft_help_prompt(
    *,
    mode: str,
    user_name: str,
    char_name: str,
    persona_text: str,
    draft: str | None,
    long_term_memory: str | None = None,
) -> str:
    if mode == "write":
        template = (
            "#写点什么\n"
            "根据当前对话，写出{{user}}接下来要发送给{{char}}的消息。\n\n"
            "请仔细观察最近的几条消息。刚才发生了什么？存在何种紧张感或发展势头？写一个能够：\n\n"
            "直接回应或延续{{char}}刚说的内容/行为\n"
            "通过新的行动、提问、揭露或情感节点推动场景发展\n"
            "符合{{user}}的语气风格，避免通用表达\n"
            "目标长度为4-8句话，形成扎实的中等篇幅回复\n"
            "自然运用Markdown格式（用斜体表示动作/内心活动）\n"
            "为{{char}}提供值得回应的内容\n\n"
            "{{user}}的Persona信息：\n（此处自动添加用户当前Persona内容）\n\n"
            "仅输出纯消息文本。不要添加引号、标签、旁白说明、元评论或“以下是”等引导语。"
        )
        template = template.replace("（此处自动添加用户当前Persona内容）", persona_text or "（无）")
        prompt = replace_placeholders_in_text(template, char_name=char_name, user_name=user_name)
        if long_term_memory and long_term_memory.strip():
            prompt = f"{prompt}\n\nLongTermMemory：\n{long_term_memory.strip()}"
        return prompt
    template = (
        "#增强消息\n"
        "根据{{user}}的以下草稿进行改写：（此处自动添加用户输入文本框内的文字。）\n\n"
        "目标：\n\n"
        "强化语言表现力，使其生动且贴合场景\n"
        "保持{{user}}真实的语气和习惯用词\n"
        "对{{char}}刚才的言行作出反应，不要回避\n"
        "推动互动进展，为{{char}}提供可回应内容\n"
        "自然运用Markdown格式（用斜体表示动作/思绪）\n"
        "若原稿较短，扩展至4-8句话；否则保持相近篇幅\n\n"
        "{{user}}的Persona信息：\n（此处自动添加用户Persona内容）"
    )
    template = template.replace("（此处自动添加用户Persona内容）", persona_text or "（无）")
    template = template.replace("（此处自动添加用户输入文本框内的文字。）", draft or "")
    prompt = replace_placeholders_in_text(template, char_name=char_name, user_name=user_name)
    if long_term_memory and long_term_memory.strip():
        prompt = f"{prompt}\n\nLongTermMemory：\n{long_term_memory.strip()}"
    return prompt


@router.post("/generate/stream")
async def generate_stream(req: GenerateStreamRequest) -> StreamingResponse:
    """
    单聊流式生成
    
    支持流式和非流式两种模式（根据settings.streamEnabled决定）。
    纯AI模式下，用户消息会映射为system角色。
    自动处理用户Persona注入、角色信息注入、长期记忆等。
    生成完成后会自动保存到聊天记录中。
    
    Args:
        req: 生成请求对象
    
    Returns:
        StreamingResponse | JSONResponse: 流式响应或JSON响应
    
    Raises:
        HTTPException: 聊天或角色不存在时抛出404错误
    """
    try:
        chat = load_chat(req.chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    settings = load_settings()
    try:
        character = load_character(chat.characterId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found for chat")

    pure_ai_mode = _resolve_pure_ai_mode(settings, chat, req.runtimeOverrides)

    if getattr(req, "appendUserMessage", True):
        user_role = "system" if pure_ai_mode else "user"
        user_display_name = getattr(req, "senderName", None) or (getattr(req, "userPersona", None).name if getattr(req, "userPersona", None) else "用户")
        char_name_for_user_input = character.name or "角色"
        replaced_user_message = replace_placeholders_in_text(
            req.userMessage,
            char_name=char_name_for_user_input,
            user_name=user_display_name or "用户",
        )
        chat.messages.append(ChatMessage(
            role=user_role,
            content=replaced_user_message,
            images=getattr(req, "userImages", []) or [],
            senderPersonaId=None if pure_ai_mode else getattr(req, "senderPersonaId", None),
            senderName=None if pure_ai_mode else getattr(req, "senderName", None),
            senderAvatar=None if pure_ai_mode else getattr(req, "senderAvatar", None),
        ))
        chat.updatedAt = _now_iso()
        save_chat(chat)

    runtime = req.runtimeOverrides
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    # 用户 persona：优先使用请求体中的 userPersona（保证首条消息等场景下即使用户未保存设置也能带上正确身份）
    persona_for_prompt = None
    if not pure_ai_mode:
        req_persona = getattr(req, "userPersona", None)
        if req_persona and (getattr(req_persona, "name", None) or getattr(req_persona, "description", None)):
            persona_for_prompt = req_persona
        if persona_for_prompt is None:
            persona_for_prompt = _resolve_selected_persona(settings, chat, pure_ai_mode)
    if persona_for_prompt:
        user_persona_parts: list[str] = []
        runtime_user_name = (persona_for_prompt.name or "").strip() or "用户"
        if persona_for_prompt.name and persona_for_prompt.name.strip():
            user_persona_parts.append(
                f"user姓名：{replace_placeholders_in_text(persona_for_prompt.name.strip(), char_name=character.name or '角色', user_name=runtime_user_name)}"
            )
        if persona_for_prompt.description and persona_for_prompt.description.strip():
            user_persona_parts.append(
                "User简介：\n"
                + replace_placeholders_in_text(
                    persona_for_prompt.description.strip(),
                    char_name=character.name or "角色",
                    user_name=runtime_user_name,
                )
            )
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))
    
    character_parts: list[str] = []
    if character.name and character.name.strip():
        character_parts.append(f"char姓名：{character.name.strip()}")
    if character.description and character.description.strip():
        character_parts.append(
            "Description：\n"
            + replace_placeholders_in_text(
                character.description.strip(),
                char_name=character.name or "角色",
                user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
            )
        )
    if character.personality and character.personality.strip():
        character_parts.append(
            "Personality：\n"
            + replace_placeholders_in_text(
                character.personality.strip(),
                char_name=character.name or "角色",
                user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
            )
        )
    if character.scenario and character.scenario.strip():
        character_parts.append(
            "Scenario：\n"
            + replace_placeholders_in_text(
                character.scenario.strip(),
                char_name=character.name or "角色",
                user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
            )
        )
    if character.exampleDialogue and character.exampleDialogue.strip():
        character_parts.append(
            "ExampleDialogue：\n"
            + replace_placeholders_in_text(
                character.exampleDialogue.strip(),
                char_name=character.name or "角色",
                user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
            )
        )
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(
            replace_placeholders_in_text(
                character.systemPrompt.strip(),
                char_name=character.name or "角色",
                user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
            )
        )
    
    if character_parts:
        prompt_parts.append("\n\n".join(character_parts))
    
    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if long_term_memory and long_term_memory.strip():
        prompt_parts.append(f"LongTermMemory：\n{long_term_memory.strip()}")

    if chat.overrides.prompt:
        prompt_parts.append(chat.overrides.prompt)
    if runtime and runtime.prompt:
        prompt_parts.append(runtime.prompt)
    system_prompt = "\n\n".join([p for p in prompt_parts if p.strip()])

    def pick_param(name: str):
        """
        选择参数值（优先级：runtime > chat.overrides > settings.generationDefaults）
        
        Args:
            name: 参数名称
        
        Returns:
            Any: 参数值
        """
        val = None
        if runtime is not None:
            val = getattr(runtime.params, name, None)
        if val is None:
            val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    model = pick_param("model") or settings.llm.defaultModel
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")
    context_size = pick_param("context_size")

    preset_id = None
    if runtime and runtime.presetId:
        preset_id = runtime.presetId
    elif chat.overrides.presetId:
        preset_id = chat.overrides.presetId
    
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey

    _apply_placeholder_rewrite_to_history(
        chat,
        default_char_name=character.name or "角色",
        fallback_user_name=(persona_for_prompt.name.strip() if persona_for_prompt and persona_for_prompt.name else "用户"),
    )

    conversation: list[dict] = []
    image_fallback_mode = bool(getattr(req, "imageFallbackMode", False))
    for m in chat.messages:
        role = "system" if pure_ai_mode and m.role == "user" else m.role
        conversation.append({
            "role": role,
            "content": _message_to_openai_content(chat, m, image_fallback_mode=image_fallback_mode),
            "_message_id": m.id,
        })

    conversation = _slice_conversation_with_anchor(
        conversation,
        getattr(chat.overrides, "contextStartMessageId", None),
    )
    system_tokens = count_tokens(system_prompt) or 0
    pretrim_budget = max(int(context_size) - system_tokens, 0) if context_size and context_size >= 1 else None
    base_conversation = trim_messages_to_context(conversation, pretrim_budget, None) if pretrim_budget is not None else list(conversation)

    worldbook_order = list(getattr(chat.overrides, "worldBookIds", []) or [])
    wb_global_excl = set(getattr(chat.overrides, "worldBookGlobalExclusions", []) or [])
    active_books = collect_active_worldbooks(chat.id, worldbook_order, wb_global_excl)
    selected_books = list(active_books)
    selected_book_ids = {book.id for book in selected_books}
    worldbook_meta: dict[str, dict[str, Any]] = {}
    worldbook_token_known = True
    worldbook_tokens_total = 0
    for book in selected_books:
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, base_conversation, eff_scan)
        injections = build_worldbook_injections(book, entries, len(base_conversation), ins_dep)
        token_count = count_tokens_for_messages([item["message"] for item in injections]) if injections else 0
        if token_count is None:
            worldbook_token_known = False
            token_count = 0
        worldbook_meta[book.id] = {"entries": entries, "injections": injections, "tokens": token_count}
        worldbook_tokens_total += token_count

    if context_size and context_size >= 1 and worldbook_token_known:
        budget = int(context_size)
        while selected_books and (system_tokens + worldbook_tokens_total) > budget:
            removed = selected_books.pop()
            selected_book_ids.discard(removed.id)
            worldbook_tokens_total -= int(worldbook_meta.get(removed.id, {}).get("tokens", 0))

    if context_size and context_size >= 1:
        history_budget = int(context_size) - system_tokens
        if worldbook_token_known:
            history_budget -= max(worldbook_tokens_total, 0)
        history_budget = max(history_budget, 0)
        conversation = trim_messages_to_context(base_conversation, history_budget, None)
    else:
        conversation = list(base_conversation)

    final_injections: list[dict[str, Any]] = []
    for book in active_books:
        if book.id not in selected_book_ids:
            continue
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, conversation, eff_scan)
        final_injections.extend(build_worldbook_injections(book, entries, len(conversation), ins_dep))
    conversation = insert_injections_into_conversation(conversation, final_injections)

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for c in conversation:
        c = dict(c)
        c.pop("_message_id", None)
        messages.append(c)

    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    extra_body = reasoning_cfg["extra_body"]
    if model == "deepseek-reasoner" or thinking_enabled:
        temperature = None

    async def event_iter() -> AsyncIterator[str]:
        full_text: list[str] = []
        try:
            async for chunk in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            ):
                if chunk.kind == "reasoning":
                    yield _sse("reasoning", {"text": chunk.text})
                else:
                    full_text.append(chunk.text)
                    yield _sse("delta", {"text": chunk.text})

            assistant_content = "".join(full_text).strip()
            if assistant_content:
                assistant_msg = ChatMessage(role="assistant", content=assistant_content)
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
                if model and model not in settings.llm.usedModels:
                    settings.llm.usedModels.insert(0, model)
                    settings.llm.usedModels = settings.llm.usedModels[:20]
                    settings.updatedAt = _now_iso()
                    save_settings(settings)
                yield _sse("done", {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id})
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            if thinking_enabled:
                resp = await chat_completions_message(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = (resp.content or "").strip()
                reasoning_content = resp.reasoning_content or None
            else:
                result = await chat_completions(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = result.text.strip()
                reasoning_content = None
            assistant_msg = None
            if assistant_content:
                assistant_msg = ChatMessage(role="assistant", content=assistant_content)
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
                if model and model not in settings.llm.usedModels:
                    settings.llm.usedModels.insert(0, model)
                    settings.llm.usedModels = settings.llm.usedModels[:20]
                    settings.updatedAt = _now_iso()
                    save_settings(settings)
            payload = {
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "content": assistant_content,
                "stream": False,
            }
            if reasoning_content is not None:
                payload["reasoningContent"] = reasoning_content
            return JSONResponse(payload)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate/draft-help")
async def generate_draft_help(req: DraftHelpRequest) -> StreamingResponse:
    """写作辅助：根据当前会话上下文生成或润色用户草稿。"""
    try:
        chat = load_chat(req.chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    settings = load_settings()
    pure_ai_mode = _resolve_pure_ai_mode(settings, chat, None)
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    user_name = (selected_persona.name if selected_persona and selected_persona.name else "用户")
    persona_text = (selected_persona.description if selected_persona and selected_persona.description else "")
    char_name = _resolve_char_name_for_draft_help(chat)
    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if req.mode == "enhance" and (req.draft is None or not req.draft.strip()):
        raise HTTPException(status_code=400, detail="draft required for enhance mode")

    instruction = _build_draft_help_prompt(
        mode=req.mode,
        user_name=user_name,
        char_name=char_name,
        persona_text=persona_text,
        draft=req.draft,
        long_term_memory=long_term_memory,
    )
    source_messages = req.conversation if req.conversation is not None else chat.messages
    recent_dialog_messages = _build_draft_help_history_messages(
        source_messages,
        fallback_user_name=user_name,
        default_char_name=char_name,
        pure_ai_mode=pure_ai_mode,
    )
    recent_dialog_messages = _slice_conversation_with_anchor(
        recent_dialog_messages,
        getattr(chat.overrides, "contextStartMessageId", None),
    )
    recent_dialog_messages = _limit_conversation_by_message_count(
        recent_dialog_messages,
        _resolve_draft_help_context_limit(settings, chat),
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instruction},
    ]

    def pick_param(name: str):
        val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    model = pick_param("model") or settings.llm.defaultModel
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")
    context_size = pick_param("context_size")
    if context_size and context_size >= 1:
        recent_dialog_messages = trim_messages_to_context(recent_dialog_messages, context_size, long_term_memory or None)
    recent_dialog = _render_draft_help_history_text(recent_dialog_messages) or "（暂无可用对话上下文）"
    messages.append({"role": "user", "content": f"最近对话如下：\n{recent_dialog}"})
    preset_id = chat.overrides.presetId
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey
    if preset_id:
        found = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found:
            base_url = found.baseUrl
            api_key = found.apiKey

    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    extra_body = reasoning_cfg["extra_body"]
    if model == "deepseek-reasoner" or thinking_enabled:
        temperature = None

    async def event_iter() -> AsyncIterator[str]:
        full_text: list[str] = []
        try:
            async for chunk in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            ):
                if chunk.kind == "reasoning":
                    yield _sse("reasoning", {"text": chunk.text})
                elif chunk.kind == "content":
                    full_text.append(chunk.text)
                    yield _sse("delta", {"text": chunk.text})
            yield _sse("done", {"ok": True, "content": "".join(full_text)})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            resp = await chat_completions_message(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
            return JSONResponse({
                "ok": True,
                "content": (resp.content or "").strip(),
                "reasoningContent": resp.reasoning_content or None,
                "stream": False,
            })
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate/group")
async def generate_group_response(req: GroupGenerateRequest) -> StreamingResponse:
    """
    群聊生成
    
    指定群聊中的某个角色进行回复，不添加新的用户消息。
    支持成员独立设置（模型、参数、API预设等）。
    消息会标注角色名称以便区分。
    
    Args:
        req: 群聊生成请求对象
    
    Returns:
        StreamingResponse | JSONResponse: 流式响应或JSON响应
    
    Raises:
        HTTPException: 聊天不存在、非群聊、角色不是成员或角色不存在时抛出相应错误
    """
    try:
        chat = load_chat(req.chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="this endpoint is for group chats only")
    
    if req.characterId not in chat.memberIds:
        raise HTTPException(status_code=400, detail="character is not a member of this group")

    settings = load_settings()
    pure_ai_mode = _resolve_pure_ai_mode(settings, chat, req.runtimeOverrides)
    try:
        character = load_character(req.characterId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")

    runtime = req.runtimeOverrides
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    runtime_user_name = selected_persona.name.strip() if selected_persona and selected_persona.name else "用户"
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(
                f"user姓名：{replace_placeholders_in_text(selected_persona.name.strip(), char_name=character.name or '角色', user_name=runtime_user_name)}"
            )
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(
                "User简介：\n"
                + replace_placeholders_in_text(
                    selected_persona.description.strip(),
                    char_name=character.name or "角色",
                    user_name=runtime_user_name,
                )
            )
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))

    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue
    
    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append("\n".join(group_context_parts))
    
    member_settings = chat.memberSettings.get(req.characterId)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    character_parts: list[str] = []
    character_parts.append(f"你现在扮演的角色是：{character.name}")
    if character.description and character.description.strip():
        character_parts.append(
            "Description：\n"
            + replace_placeholders_in_text(
                character.description.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if include_personality and character.personality and character.personality.strip():
        character_parts.append(
            "Personality：\n"
            + replace_placeholders_in_text(
                character.personality.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if include_scenario and character.scenario and character.scenario.strip():
        character_parts.append(
            "Scenario：\n"
            + replace_placeholders_in_text(
                character.scenario.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(
            replace_placeholders_in_text(
                character.systemPrompt.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    
    if character_parts:
        prompt_parts.append("\n\n".join(character_parts))
    
    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if long_term_memory and long_term_memory.strip():
        prompt_parts.append(f"LongTermMemory：\n{long_term_memory.strip()}")

    if chat.overrides.prompt:
        prompt_parts.append(chat.overrides.prompt)
    if runtime and runtime.prompt:
        prompt_parts.append(runtime.prompt)
    system_prompt = "\n\n".join([p for p in prompt_parts if p.strip()])

    def pick_param(name: str):
        """
        选择参数值（优先级：runtime > memberSettings > chat.overrides > settings.generationDefaults）
        
        Args:
            name: 参数名称
        
        Returns:
            Any: 参数值
        """
        val = None
        if runtime is not None:
            val = getattr(runtime.params, name, None)
        if val is None and member_settings is not None:
            val = getattr(member_settings, name, None)
        if val is None:
            val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    model = None
    if member_settings and member_settings.model:
        model = member_settings.model
    if not model:
        model = pick_param("model") or settings.llm.defaultModel
    
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")
    context_size = pick_param("context_size")

    preset_id = None
    if member_settings and member_settings.presetId:
        preset_id = member_settings.presetId
    elif runtime and runtime.presetId:
        preset_id = runtime.presetId
    elif chat.overrides.presetId:
        preset_id = chat.overrides.presetId
    
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey

    _apply_placeholder_rewrite_to_history(
        chat,
        default_char_name=character.name or "角色",
        fallback_user_name=runtime_user_name,
    )
    image_fallback_mode = bool(getattr(req, "imageFallbackMode", False))
    conversation: list[dict] = []
    char_name_cache: dict[str, str] = {}
    for m in chat.messages:
        char_name_for_message = _resolve_char_name_for_history_message(
            m,
            default_char_name=character.name or "角色",
            character_name_cache=char_name_cache,
        )
        raw_content = _message_to_openai_content(chat, m, image_fallback_mode=image_fallback_mode)
        if m.role == "user":
            if pure_ai_mode:
                prefix = f"[{_resolve_user_name_for_message(m, runtime_user_name)}]: "
                content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
                conversation.append({"role": "system", "content": content, "_message_id": m.id})
            else:
                user_name = _resolve_user_name_for_message(m, runtime_user_name)
                prefix = f"[{user_name}]: "
                content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
                conversation.append({"role": "user", "content": content, "_message_id": m.id})
        elif m.role == "assistant":
            prefix = f"[{char_name_for_message}]: "
            content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
            conversation.append({"role": "assistant", "content": content, "_message_id": m.id})
        else:
            conversation.append({"role": m.role, "content": raw_content, "_message_id": m.id})
    conversation = _slice_conversation_with_anchor(
        conversation,
        getattr(chat.overrides, "contextStartMessageId", None),
    )
    system_tokens = count_tokens(system_prompt) or 0
    pretrim_budget = max(int(context_size) - system_tokens, 0) if context_size and context_size >= 1 else None
    base_conversation = trim_messages_to_context(conversation, pretrim_budget, None) if pretrim_budget is not None else list(conversation)

    worldbook_order = list(getattr(chat.overrides, "worldBookIds", []) or [])
    wb_global_excl = set(getattr(chat.overrides, "worldBookGlobalExclusions", []) or [])
    active_books = collect_active_worldbooks(chat.id, worldbook_order, wb_global_excl)
    selected_books = list(active_books)
    selected_book_ids = {book.id for book in selected_books}
    worldbook_meta: dict[str, dict[str, Any]] = {}
    worldbook_token_known = True
    worldbook_tokens_total = 0
    for book in selected_books:
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, base_conversation, eff_scan)
        injections = build_worldbook_injections(book, entries, len(base_conversation), ins_dep)
        token_count = count_tokens_for_messages([item["message"] for item in injections]) if injections else 0
        if token_count is None:
            worldbook_token_known = False
            token_count = 0
        worldbook_meta[book.id] = {"entries": entries, "injections": injections, "tokens": token_count}
        worldbook_tokens_total += token_count

    if context_size and context_size >= 1 and worldbook_token_known:
        budget = int(context_size)
        while selected_books and (system_tokens + worldbook_tokens_total) > budget:
            removed = selected_books.pop()
            selected_book_ids.discard(removed.id)
            worldbook_tokens_total -= int(worldbook_meta.get(removed.id, {}).get("tokens", 0))

    if context_size and context_size >= 1:
        history_budget = int(context_size) - system_tokens
        if worldbook_token_known:
            history_budget -= max(worldbook_tokens_total, 0)
        history_budget = max(history_budget, 0)
        conversation = trim_messages_to_context(base_conversation, history_budget, None)
    else:
        conversation = list(base_conversation)

    final_injections: list[dict[str, Any]] = []
    for book in active_books:
        if book.id not in selected_book_ids:
            continue
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, conversation, eff_scan)
        final_injections.extend(build_worldbook_injections(book, entries, len(conversation), ins_dep))
    conversation = insert_injections_into_conversation(conversation, final_injections)

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for c in conversation:
        c = dict(c)
        c.pop("_message_id", None)
        messages.append(c)

    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    extra_body = reasoning_cfg["extra_body"]
    if model == "deepseek-reasoner" or thinking_enabled:
        temperature = None

    async def event_iter():
        full_text: list[str] = []
        try:
            async for chunk in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            ):
                if chunk.kind == "reasoning":
                    yield _sse("reasoning", {"text": chunk.text})
                else:
                    full_text.append(chunk.text)
                    yield _sse("delta", {"text": chunk.text})

            assistant_content = "".join(full_text).strip()
            if assistant_content:
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_content,
                    characterId=req.characterId
                )
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
                yield _sse("done", {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id, "characterId": req.characterId})
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id, "characterId": req.characterId})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            if thinking_enabled:
                resp = await chat_completions_message(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = (resp.content or "").strip()
                reasoning_content = resp.reasoning_content or None
            else:
                result = await chat_completions(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = result.text.strip()
                reasoning_content = None
            assistant_msg = None
            if assistant_content:
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_content,
                    characterId=req.characterId
                )
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
            payload = {
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "characterId": req.characterId,
                "content": assistant_content,
                "stream": False,
            }
            if reasoning_content is not None:
                payload["reasoningContent"] = reasoning_content
            return JSONResponse(payload)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate/interject")
async def generate_single_interject(req: SingleInterjectRequest) -> StreamingResponse:
    """
    群聊单次插话
    
    让群聊中的指定角色额外回复一次，不添加新的用户消息。
    用于在轮次结束后让某个角色进行额外的插话。
    
    Args:
        req: 插话请求对象
    
    Returns:
        StreamingResponse | JSONResponse: 流式响应或JSON响应
    
    Raises:
        HTTPException: 聊天不存在、非群聊、角色不是成员或角色不存在时抛出相应错误
    """
    try:
        chat = load_chat(req.chatId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="this endpoint is for group chats only")
    
    if req.characterId not in chat.memberIds:
        raise HTTPException(status_code=400, detail="character is not a member of this group")

    settings = load_settings()
    pure_ai_mode = _resolve_pure_ai_mode(settings, chat, None)
    try:
        character = load_character(req.characterId)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")

    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    runtime_user_name = selected_persona.name.strip() if selected_persona and selected_persona.name else "用户"
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(
                f"user姓名：{replace_placeholders_in_text(selected_persona.name.strip(), char_name=character.name or '角色', user_name=runtime_user_name)}"
            )
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(
                "User简介：\n"
                + replace_placeholders_in_text(
                    selected_persona.description.strip(),
                    char_name=character.name or "角色",
                    user_name=runtime_user_name,
                )
            )
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))

    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue
    
    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append("\n".join(group_context_parts))
    
    member_settings = chat.memberSettings.get(req.characterId)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    character_parts: list[str] = []
    character_parts.append(f"你现在扮演的角色是：{character.name}")
    character_parts.append("请根据当前对话内容进行回复（这是一次额外的插话机会）。")
    if character.description and character.description.strip():
        character_parts.append(
            "Description：\n"
            + replace_placeholders_in_text(
                character.description.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if include_personality and character.personality and character.personality.strip():
        character_parts.append(
            "Personality：\n"
            + replace_placeholders_in_text(
                character.personality.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if include_scenario and character.scenario and character.scenario.strip():
        character_parts.append(
            "Scenario：\n"
            + replace_placeholders_in_text(
                character.scenario.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(
            replace_placeholders_in_text(
                character.systemPrompt.strip(),
                char_name=character.name or "角色",
                user_name=runtime_user_name,
            )
        )
    
    if character_parts:
        prompt_parts.append("\n\n".join(character_parts))
    
    long_term_memory = getattr(chat.overrides, "longTermMemory", None)
    if long_term_memory and long_term_memory.strip():
        prompt_parts.append(f"LongTermMemory：\n{long_term_memory.strip()}")

    if chat.overrides.prompt:
        prompt_parts.append(chat.overrides.prompt)
    system_prompt = "\n\n".join([p for p in prompt_parts if p.strip()])

    def pick_param(name: str):
        """
        选择参数值（优先级：memberSettings > chat.overrides > settings.generationDefaults）
        
        Args:
            name: 参数名称
        
        Returns:
            Any: 参数值
        """
        val = None
        if member_settings is not None:
            val = getattr(member_settings, name, None)
        if val is None:
            val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    model = None
    if member_settings and member_settings.model:
        model = member_settings.model
    if not model:
        model = pick_param("model") or settings.llm.defaultModel
    
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")
    context_size = pick_param("context_size")

    preset_id = None
    if member_settings and member_settings.presetId:
        preset_id = member_settings.presetId
    elif chat.overrides.presetId:
        preset_id = chat.overrides.presetId
    
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey

    _apply_placeholder_rewrite_to_history(
        chat,
        default_char_name=character.name or "角色",
        fallback_user_name=runtime_user_name,
    )
    image_fallback_mode = bool(getattr(req, "imageFallbackMode", False))
    conversation: list[dict] = []
    char_name_cache: dict[str, str] = {}
    for m in chat.messages:
        char_name_for_message = _resolve_char_name_for_history_message(
            m,
            default_char_name=character.name or "角色",
            character_name_cache=char_name_cache,
        )
        raw_content = _message_to_openai_content(chat, m, image_fallback_mode=image_fallback_mode)
        if m.role == "user":
            if pure_ai_mode:
                prefix = f"[{_resolve_user_name_for_message(m, runtime_user_name)}]: "
                content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
                conversation.append({"role": "system", "content": content, "_message_id": m.id})
            else:
                user_name = _resolve_user_name_for_message(m, runtime_user_name)
                prefix = f"[{user_name}]: "
                content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
                conversation.append({"role": "user", "content": content, "_message_id": m.id})
        elif m.role == "assistant":
            prefix = f"[{char_name_for_message}]: "
            content = f"{prefix}{raw_content}" if isinstance(raw_content, str) else [{"type": "text", "text": prefix}, *raw_content]
            conversation.append({"role": "assistant", "content": content, "_message_id": m.id})
        else:
            conversation.append({"role": m.role, "content": raw_content, "_message_id": m.id})
    conversation = _slice_conversation_with_anchor(
        conversation,
        getattr(chat.overrides, "contextStartMessageId", None),
    )
    system_tokens = count_tokens(system_prompt) or 0
    pretrim_budget = max(int(context_size) - system_tokens, 0) if context_size and context_size >= 1 else None
    base_conversation = trim_messages_to_context(conversation, pretrim_budget, None) if pretrim_budget is not None else list(conversation)

    worldbook_order = list(getattr(chat.overrides, "worldBookIds", []) or [])
    wb_global_excl = set(getattr(chat.overrides, "worldBookGlobalExclusions", []) or [])
    active_books = collect_active_worldbooks(chat.id, worldbook_order, wb_global_excl)
    selected_books = list(active_books)
    selected_book_ids = {book.id for book in selected_books}
    worldbook_meta: dict[str, dict[str, Any]] = {}
    worldbook_token_known = True
    worldbook_tokens_total = 0
    for book in selected_books:
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, base_conversation, eff_scan)
        injections = build_worldbook_injections(book, entries, len(base_conversation), ins_dep)
        token_count = count_tokens_for_messages([item["message"] for item in injections]) if injections else 0
        if token_count is None:
            worldbook_token_known = False
            token_count = 0
        worldbook_meta[book.id] = {"entries": entries, "injections": injections, "tokens": token_count}
        worldbook_tokens_total += token_count

    if context_size and context_size >= 1 and worldbook_token_known:
        budget = int(context_size)
        while selected_books and (system_tokens + worldbook_tokens_total) > budget:
            removed = selected_books.pop()
            selected_book_ids.discard(removed.id)
            worldbook_tokens_total -= int(worldbook_meta.get(removed.id, {}).get("tokens", 0))

    if context_size and context_size >= 1:
        history_budget = int(context_size) - system_tokens
        if worldbook_token_known:
            history_budget -= max(worldbook_tokens_total, 0)
        history_budget = max(history_budget, 0)
        conversation = trim_messages_to_context(base_conversation, history_budget, None)
    else:
        conversation = list(base_conversation)

    final_injections: list[dict[str, Any]] = []
    for book in active_books:
        if book.id not in selected_book_ids:
            continue
        eff_scan, ins_dep = _runtime_scan_insert_for_book(book.id, chat, settings)
        entries = match_worldbook_entries(book, conversation, eff_scan)
        final_injections.extend(build_worldbook_injections(book, entries, len(conversation), ins_dep))
    conversation = insert_injections_into_conversation(conversation, final_injections)

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for c in conversation:
        c = dict(c)
        c.pop("_message_id", None)
        messages.append(c)

    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    extra_body = reasoning_cfg["extra_body"]
    if model == "deepseek-reasoner" or thinking_enabled:
        temperature = None

    async def event_iter():
        full_text: list[str] = []
        try:
            async for chunk in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            ):
                if chunk.kind == "reasoning":
                    yield _sse("reasoning", {"text": chunk.text})
                else:
                    full_text.append(chunk.text)
                    yield _sse("delta", {"text": chunk.text})

            assistant_content = "".join(full_text).strip()
            if assistant_content:
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_content,
                    characterId=req.characterId
                )
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
                yield _sse("done", {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id, "characterId": req.characterId, "isInterject": True})
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id, "characterId": req.characterId, "isInterject": True})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            if thinking_enabled:
                resp = await chat_completions_message(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = (resp.content or "").strip()
                reasoning_content = resp.reasoning_content or None
            else:
                result = await chat_completions(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
                assistant_content = result.text.strip()
                reasoning_content = None
            assistant_msg = None
            if assistant_content:
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=assistant_content,
                    characterId=req.characterId
                )
                chat.messages.append(assistant_msg)
                chat.updatedAt = _now_iso()
                save_chat(chat)
            payload = {
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "characterId": req.characterId,
                "content": assistant_content,
                "stream": False,
                "isInterject": True,
            }
            if reasoning_content is not None:
                payload["reasoningContent"] = reasoning_content
            return JSONResponse(payload)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
