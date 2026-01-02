from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.llm.openai_compat import chat_completions, stream_chat_completions
from app.schemas import ChatMessage, GenerateStreamRequest
from app.storage import load_character, load_chat, load_settings, save_chat, save_settings


router = APIRouter(tags=["generate"])


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


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

    # 先落盘保存用户消息（即使后续模型调用失败也保留用户输入）
    chat.messages.append(ChatMessage(role="user", content=req.userMessage))
    chat.updatedAt = _now_iso()
    save_chat(chat)

    # 组装 prompt/参数优先级：runtimeOverrides > chat.overrides > settings.defaults
    runtime = req.runtimeOverrides
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)
    
    # 构建用户Persona相关提示词
    selected_persona = None
    if settings.selectedPersonaId and settings.userPersonas:
        selected_persona = next((p for p in settings.userPersonas if p.id == settings.selectedPersonaId), None)
    
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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for m in chat.messages:
        messages.append({"role": m.role, "content": m.content})

    async def event_iter() -> AsyncIterator[str]:
        full_text: list[str] = []
        try:
            async for delta in stream_chat_completions(
                base_url=settings.llm.baseUrl,
                api_key=settings.llm.apiKey,
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
                
                # 保存使用过的模型到 usedModels 列表
                if model and model not in settings.llm.usedModels:
                    settings.llm.usedModels.insert(0, model)
                    # 限制最多保存 20 个使用过的模型
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
                base_url=settings.llm.baseUrl,
                api_key=settings.llm.apiKey,
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
                
                # 保存使用过的模型到 usedModels 列表
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


