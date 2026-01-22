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
    return datetime.now().astimezone().isoformat()

def _resolve_pure_ai_mode(settings, chat, runtime) -> bool:
    # runtimeOverrides > chat.overrides > settings
    if runtime is not None and getattr(runtime, "pureAiMode", None) is not None:
        return bool(runtime.pureAiMode)
    if chat is not None and getattr(chat, "overrides", None) is not None and getattr(chat.overrides, "pureAiMode", None) is not None:
        return bool(chat.overrides.pureAiMode)
    return bool(getattr(settings, "pureAiMode", False))


def _resolve_selected_persona(settings, chat, pure_ai_mode):
    if pure_ai_mode:
        return None
    persona_id = getattr(chat, "userPersonaId", None) or getattr(settings, "selectedPersonaId", None)
    if not persona_id or not getattr(settings, "userPersonas", None):
        return None
    return next((p for p in settings.userPersonas if p.id == persona_id), None)


def _sse(event: str, data_obj: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


@router.post("/generate/stream")
async def generate_stream(req: GenerateStreamRequest) -> StreamingResponse:
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

    # 先落盘保存用户消息（即使后续模型调用失败也保留用户输入）
    # 纯 AI 模式：用户发言以 system 身份影响世界/规则
    # appendUserMessage=False 用于重写场景避免重复添加用户消息
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

    # 组装 prompt/参数优先级：runtimeOverrides > chat.overrides > settings.defaults
    runtime = req.runtimeOverrides
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    # 构建用户Persona相关提示词
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))
    
    # 构建角色相关提示词
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

    # 确定 API 配置 (Preset > Global)
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
            # 兼容历史记录：旧版本可能把用户消息存为 user
            messages.append({"role": "system", "content": m.content})
        else:
            messages.append({"role": m.role, "content": m.content})

    async def event_iter() -> AsyncIterator[str]:
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
                
                # 保存使用过的模型到 usedModels 列表 (不再保存)
                # 注意：如果使用了预设，这里的 usedModels 逻辑可能需要调整，
                # 但为了兼容性，我们依然更新全局的 usedModels，或者后续前端自行管理
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

    # 检查是否启用流式传输
    if not settings.streamEnabled:
        # 非流式模式：直接调用并返回完整结果
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
    """群聊生成 - 指定角色回复，不添加新的用户消息"""
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

    # 组装 prompt/参数
    runtime = req.runtimeOverrides
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    # 构建用户Persona相关提示词
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))

    # 群聊场景：构建所有角色的信息
    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue
    
    # 构建群聊上下文
    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append("\n".join(group_context_parts))
    
    # 获取该角色的独立设置（含 prompt 插入字段开关）
    member_settings = chat.memberSettings.get(req.characterId)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    # 构建当前回复角色的提示词
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
        val = None
        # 优先级: runtime > memberSettings > chat.overrides > settings.generationDefaults
        if runtime is not None:
            val = getattr(runtime.params, name, None)
        if val is None and member_settings is not None:
            val = getattr(member_settings, name, None)
        if val is None:
            val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    # 模型选择优先级: memberSettings.model > chat.overrides.params.model > settings.llm.defaultModel
    model = None
    if member_settings and member_settings.model:
        model = member_settings.model
    if not model:
        model = pick_param("model") or settings.llm.defaultModel
    
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")

    # 确定 API 配置 (memberSettings.presetId > runtime.presetId > chat.overrides.presetId > Global)
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

    # 构建消息列表，为群聊格式化历史消息
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    for m in chat.messages:
        if m.role == "user":
            # 用户消息（纯 AI 模式下映射为 system）
            if pure_ai_mode:
                messages.append({"role": "system", "content": f"[用户]: {m.content}"})
            else:
                user_name = getattr(m, "senderName", None) or (selected_persona.name if selected_persona else "用户")
                messages.append({"role": "user", "content": f"[{user_name}]: {m.content}"})
        elif m.role == "assistant":
            # 角色消息 - 标注是哪个角色说的
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
                # 保存消息，标记 characterId
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

    # 检查是否启用流式传输
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
    """单次插话 - 让指定角色额外回复一次（不添加用户消息）"""
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

    # 组装 prompt/参数
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    # 构建用户Persona相关提示词
    selected_persona = _resolve_selected_persona(settings, chat, pure_ai_mode)
    if selected_persona:
        user_persona_parts: list[str] = []
        if selected_persona.name and selected_persona.name.strip():
            user_persona_parts.append(f"user姓名：{selected_persona.name.strip()}")
        if selected_persona.description and selected_persona.description.strip():
            user_persona_parts.append(f"User简介：\n{selected_persona.description.strip()}")
        if user_persona_parts:
            prompt_parts.append("\n".join(user_persona_parts))

    # 群聊场景：构建所有角色的信息
    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue
    
    # 构建群聊上下文
    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append("\n".join(group_context_parts))
    
    # 获取该角色的独立设置（含 prompt 插入字段开关）
    member_settings = chat.memberSettings.get(req.characterId)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    # 构建当前回复角色的提示词
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
        val = None
        if member_settings is not None:
            val = getattr(member_settings, name, None)
        if val is None:
            val = getattr(chat.overrides.params, name, None)
        if val is None:
            val = getattr(settings.generationDefaults, name, None)
        return val

    # 模型选择优先级: memberSettings.model > chat.overrides.params.model > settings.llm.defaultModel
    model = None
    if member_settings and member_settings.model:
        model = member_settings.model
    if not model:
        model = pick_param("model") or settings.llm.defaultModel
    
    temperature = pick_param("temperature")
    top_p = pick_param("top_p")
    max_tokens = pick_param("max_tokens")

    # 确定 API 配置
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

    # 构建消息列表
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

    # 检查是否启用流式传输
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
