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

import json
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.llm.openai_compat import chat_completions, stream_chat_completions
from app.schemas import ChatMessage, GenerateStreamRequest, GroupGenerateRequest, SingleInterjectRequest
from app.storage import load_character, load_chat, load_settings, save_chat, save_settings


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
        chat.messages.append(ChatMessage(
            role=user_role,
            content=req.userMessage,
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
    
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))
    
    character_parts: list[str] = []
    if character.name and character.name.strip():
        character_parts.append(f"char姓名：{character.name.strip()}")
    if character.personality and character.personality.strip():
        character_parts.append(f"Personality：\n{character.personality.strip()}")
    if character.scenario and character.scenario.strip():
        character_parts.append(f"Scenario：\n{character.scenario.strip()}")
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(character.systemPrompt.strip())
    
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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for m in chat.messages:
        if pure_ai_mode and m.role == "user":
            messages.append({"role": "system", "content": m.content})
        else:
            messages.append({"role": m.role, "content": m.content})

    async def event_iter() -> AsyncIterator[str]:
        """
        流式事件迭代器
        
        Yields:
            str: SSE格式的事件字符串
        """
        full_text: list[str] = []
        try:
            async for delta in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            ):
                full_text.append(delta.text)
                yield _sse("delta", {"text": delta.text})

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
                
                yield _sse(
                    "done",
                    {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id},
                )
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            result = await chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            assistant_content = result.text.strip()
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
            
            return JSONResponse({
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "content": assistant_content,
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
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
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
    if include_personality and character.personality and character.personality.strip():
        character_parts.append(f"Personality：\n{character.personality.strip()}")
    if include_scenario and character.scenario and character.scenario.strip():
        character_parts.append(f"Scenario：\n{character.scenario.strip()}")
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(character.systemPrompt.strip())
    
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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    for m in chat.messages:
        if m.role == "user":
            if pure_ai_mode:
                messages.append({"role": "system", "content": f"[用户]: {m.content}"})
            else:
                user_name = getattr(m, "senderName", None) or (selected_persona.name if selected_persona else "用户")
                messages.append({"role": "user", "content": f"[{user_name}]: {m.content}"})
        elif m.role == "assistant":
            if m.characterId:
                try:
                    msg_char = load_character(m.characterId)
                    messages.append({"role": "assistant", "content": f"[{msg_char.name}]: {m.content}"})
                except FileNotFoundError:
                    messages.append({"role": "assistant", "content": m.content})
            else:
                messages.append({"role": "assistant", "content": m.content})
        else:
            messages.append({"role": m.role, "content": m.content})

    async def event_iter():
        """
        流式事件迭代器
        
        Yields:
            str: SSE格式的事件字符串
        """
        full_text: list[str] = []
        try:
            async for delta in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            ):
                full_text.append(delta.text)
                yield _sse("delta", {"text": delta.text})

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
                
                yield _sse(
                    "done",
                    {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id, "characterId": req.characterId},
                )
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id, "characterId": req.characterId})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            result = await chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            assistant_content = result.text.strip()
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
            
            return JSONResponse({
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "characterId": req.characterId,
                "content": assistant_content,
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
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
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
    if include_personality and character.personality and character.personality.strip():
        character_parts.append(f"Personality：\n{character.personality.strip()}")
    if include_scenario and character.scenario and character.scenario.strip():
        character_parts.append(f"Scenario：\n{character.scenario.strip()}")
    if character.systemPrompt and character.systemPrompt.strip():
        character_parts.append(character.systemPrompt.strip())
    
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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    for m in chat.messages:
        if m.role == "user":
            if pure_ai_mode:
                messages.append({"role": "system", "content": f"[用户]: {m.content}"})
            else:
                user_name = getattr(m, "senderName", None) or (selected_persona.name if selected_persona else "用户")
                messages.append({"role": "user", "content": f"[{user_name}]: {m.content}"})
        elif m.role == "assistant":
            if m.characterId:
                try:
                    msg_char = load_character(m.characterId)
                    messages.append({"role": "assistant", "content": f"[{msg_char.name}]: {m.content}"})
                except FileNotFoundError:
                    messages.append({"role": "assistant", "content": m.content})
            else:
                messages.append({"role": "assistant", "content": m.content})
        else:
            messages.append({"role": m.role, "content": m.content})

    async def event_iter():
        """
        流式事件迭代器
        
        Yields:
            str: SSE格式的事件字符串
        """
        full_text: list[str] = []
        try:
            async for delta in stream_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            ):
                full_text.append(delta.text)
                yield _sse("delta", {"text": delta.text})

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
                
                yield _sse(
                    "done",
                    {"ok": True, "chatId": chat.id, "assistantMessageId": assistant_msg.id, "characterId": req.characterId, "isInterject": True},
                )
            else:
                yield _sse("done", {"ok": True, "chatId": chat.id, "characterId": req.characterId, "isInterject": True})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    if not settings.streamEnabled:
        try:
            result = await chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            assistant_content = result.text.strip()
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
            
            return JSONResponse({
                "ok": True,
                "chatId": chat.id,
                "assistantMessageId": assistant_msg.id if assistant_msg else None,
                "characterId": req.characterId,
                "content": assistant_content,
                "stream": False,
                "isInterject": True,
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
