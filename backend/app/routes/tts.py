"""
TTS 路由模块

提供语音合成、音色查询、缓存统计与清空等接口。
所有 /api/tts/* 路由在 ttsEnabled == false 时返回 403。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import json

from app.assistant import load_tts_post_process_prompt
from app.llm.openai_compat import chat_completions
from app.schemas import Settings
from app.services.tts_cache import tts_cache_patrol
from app.services.tts_platform import MiniMaxTtsPlatform, SynthesisRequest
from app.storage import get_tts_cache_dir, load_chat, load_settings, save_chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tts", tags=["tts"])

EMOTION_TAG_HINTS = [
    "(laughs)",
    "(chuckle)",
    "(coughs)",
    "(clear-throat)",
    "(groans)",
    "(breath)",
    "(pant)",
    "(inhale)",
    "(exhale)",
    "(gasps)",
    "(sniffs)",
    "(sighs)",
    "(snorts)",
    "(humming)",
    "(whistles)",
]

EMOTION_TAGS_DIRECTIVE = (
    "You may insert MiniMax-compatible English speech tags only when they are clearly justified by the text. "
    f"Allowed tags: {', '.join(EMOTION_TAG_HINTS)}. "
    "Do not invent unsupported tags. Do not overuse tags."
)


# ---------------------------------------------------------------------------
# 守卫：TTS 总开关
# ---------------------------------------------------------------------------

def _require_tts_enabled() -> Settings:
    """加载设置并验证 TTS 已启用，否则 403。"""
    settings = load_settings()
    if not settings.ttsEnabled:
        raise HTTPException(status_code=403, detail="TTS disabled")
    return settings


def _resolve_tts_preset(settings: Settings, preset_id: str | None = None):
    """从设置中解析一个已标记为 TTS 服务的预设。"""
    if preset_id:
        for preset in settings.apiPresets:
            if preset.id == preset_id and preset.presetKind == "minimax":
                return preset
        raise HTTPException(status_code=400, detail="指定的 TTS 预设不存在，或未标记为 TTS 服务")

    for preset in settings.apiPresets:
        if preset.presetKind == "minimax":
            return preset

    raise HTTPException(status_code=400, detail="未配置 MiniMax TTS API 预设（需在 API 预设中勾选 TTS 服务）")


def _get_platform(settings: Settings, preset_id: str | None = None) -> MiniMaxTtsPlatform:
    """根据当前设置构建 MiniMax 平台实例。

    后续支持多平台时可按 presetKind 分派。
    """
    matched = _resolve_tts_preset(settings, preset_id)
    if not matched.apiKey:
        raise HTTPException(status_code=400, detail="TTS 预设缺少 API Key")
    return MiniMaxTtsPlatform(api_key=matched.apiKey, base_url=matched.baseUrl or "https://api.minimaxi.com")


def _get_inline_platform(base_url: str, api_key: str) -> MiniMaxTtsPlatform:
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="TTS API Key 不能为空")
    return MiniMaxTtsPlatform(api_key=api_key.strip(), base_url=(base_url or "https://api.minimaxi.com").strip())


def _resolve_llm_credentials(
    settings: Settings,
    *,
    preset_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str]:
    if api_key and api_key.strip():
        return ((base_url or settings.llm.baseUrl).strip(), api_key.strip())
    if preset_id:
        for preset in settings.apiPresets:
            if preset.id == preset_id:
                if not preset.apiKey.strip():
                    raise HTTPException(status_code=400, detail="后处理模型关联的 API 预设缺少 API Key")
                return ((preset.baseUrl or settings.llm.baseUrl).strip(), preset.apiKey.strip())
        raise HTTPException(status_code=400, detail="后处理模型关联的 API 预设不存在")
    if settings.llm.apiKey.strip():
        return (settings.llm.baseUrl.strip(), settings.llm.apiKey.strip())
    raise HTTPException(status_code=400, detail="未配置文本模型 API Key")


def _write_asset_id_to_message(
    chat_id: str | None,
    message_id: str | None,
    asset_id: str,
    *,
    source_text: str | None = None,
) -> None:
    """将合成后的音频 UUID 回写到消息，便于后续复用缓存。"""
    if not chat_id or not message_id:
        return

    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        logger.warning("[TTS] chat not found when binding asset", extra={"chat_id": chat_id, "message_id": message_id})
        return

    updated = False
    for index, message in enumerate(chat.messages):
        if message.id != message_id:
            continue
        payload = message.model_dump(mode="json")
        payload["ttsAudioAssetId"] = asset_id
        if source_text is not None:
            payload["ttsAudioSourceText"] = source_text
        chat.messages[index] = type(message).model_validate(payload)
        chat.updatedAt = datetime.now().astimezone().isoformat()
        updated = True
        break

    if updated:
        save_chat(chat)
    else:
        logger.warning("[TTS] message not found when binding asset", extra={"chat_id": chat_id, "message_id": message_id})


def _store_preview_audio(audio_bytes: bytes, audio_format: str = "mp3") -> str:
    asset_id = uuid4().hex
    cache_dir = get_tts_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{asset_id}.{audio_format}"
    cache_path.write_bytes(audio_bytes)
    return asset_id


def _llm_message_content_to_text(content: Any) -> str:
    """OpenAI 兼容接口里 content 可能是 string 或 content-parts 数组。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content)


def _strip_markdown_json_fence(s: str) -> str:
    """去掉 ``` / ```json 围栏，便于解析。"""
    t = s.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```(?:json|JSON)?\s*\n?", "", t, count=1)
    t = re.sub(r"\n?```\s*$", "", t, count=1)
    return t.strip()


def _first_balanced_json_object(s: str) -> str | None:
    """从任意前缀/后缀文字中截取第一个花括号平衡的 JSON 对象子串。"""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _parse_preprocess_json_payload(raw: str) -> dict[str, Any]:
    """
    解析后处理模型返回的 JSON；兼容纯 JSON、Markdown 代码块、前后说明文字。
    """
    text = _llm_message_content_to_text(raw).strip()
    if not text:
        raise ValueError("empty LLM response")

    candidates: list[str] = []
    fenced = _strip_markdown_json_fence(text)
    candidates.append(fenced)
    if fenced != text:
        candidates.append(text.strip())

    for blob in candidates:
        blob = blob.strip()
        if not blob:
            continue
        try:
            out = json.loads(blob)
            if isinstance(out, dict):
                return out
        except json.JSONDecodeError:
            pass
        inner = _first_balanced_json_object(blob)
        if inner:
            try:
                out = json.loads(inner)
                if isinstance(out, dict):
                    return out
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("no valid JSON object in LLM response", text, 0)


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class SynthesizeReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    content_text: str | None = Field(default=None, min_length=1, max_length=10000)
    voice_id: str = Field(..., min_length=1)
    model: str = "speech-2.8-hd"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, gt=0.0, le=10.0)
    pitch: int = Field(default=0, ge=-12, le=12)
    emotion: str | None = None
    audio_format: str = "mp3"
    sample_rate: int = 32000
    stream: bool = False
    message_id: str | None = None  # 关联消息 ID（用于写回 ttsAudioAssetId）
    chat_id: str | None = None
    preset_id: str | None = None


class VoicesReq(BaseModel):
    voice_type: str = "all"


class TestVoicesReq(BaseModel):
    baseUrl: str
    apiKey: str
    voice_type: str = "all"


class PreprocessReq(BaseModel):
    text: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    preset_id: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    inject_emotion_tags: bool = False
    target_language: str | None = None


class DesignVoiceReq(BaseModel):
    baseUrl: str
    apiKey: str
    prompt: str = Field(..., min_length=1)
    preview_text: str = Field(..., min_length=1, max_length=500)
    voice_id: str | None = None
    aigc_watermark: bool = False


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.get("/cache/stats")
def get_cache_stats():
    """返回缓存统计（ttsEnabled 关闭时仍允许查询，返回 usedBytes=0）。"""
    settings = load_settings()
    if not settings.ttsEnabled:
        return {
            "usedBytes": 0,
            "limitBytes": settings.ttsAudioCacheLimitMb * 1024 * 1024,
            "lastPatrolAt": "",
            "prunedFiles": 0,
        }
    return tts_cache_patrol.get_stats()


@router.delete("/cache/clear")
async def clear_cache():
    """手动清空 TTS 缓存。"""
    _require_tts_enabled()
    return await tts_cache_patrol.clear_all()


@router.post("/synthesize")
async def synthesize(req: SynthesizeReq):
    """合成语音（非流式/流式）。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings, req.preset_id)

    synth_req = SynthesisRequest(
        text=req.text,
        voice_id=req.voice_id,
        model=req.model,
        speed=req.speed,
        volume=req.volume,
        pitch=req.pitch,
        emotion=req.emotion,
        audio_format=req.audio_format,
        sample_rate=req.sample_rate,
        stream=req.stream,
    )

    try:
        if req.stream:
            async def stream_gen():
                try:
                    async for chunk in platform.synthesize_stream(synth_req):
                        yield chunk
                finally:
                    await platform.close()

            media_type = "audio/mpeg" if req.audio_format == "mp3" else f"audio/{req.audio_format}"
            return StreamingResponse(stream_gen(), media_type=media_type)
        else:
            result = await platform.synthesize(synth_req)
            await platform.close()

            # 写入缓存文件
            asset_id = uuid4().hex
            cache_dir = get_tts_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            ext = result.format or "mp3"
            cache_path = cache_dir / f"{asset_id}.{ext}"
            cache_path.write_bytes(result.audio_bytes)
            _write_asset_id_to_message(
                req.chat_id,
                req.message_id,
                asset_id,
                source_text=req.content_text or req.text,
            )

            return {
                "assetId": asset_id,
                "format": result.format,
                "sampleRate": result.sample_rate,
                "sizeBytes": len(result.audio_bytes),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TTS] synthesize error")
        await platform.close()
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/audio/{asset_id}")
def get_audio(asset_id: str):
    """通过 UUID 获取已缓存的音频文件。"""
    # 校验 asset_id 格式防止路径遍历
    if not asset_id.isalnum() or len(asset_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    cache_dir = get_tts_cache_dir()
    # 搜索匹配的文件（uuid.ext）
    for f in cache_dir.iterdir():
        if f.is_file() and f.stem == asset_id:
            media_type = "audio/mpeg" if f.suffix == ".mp3" else f"audio/{f.suffix.lstrip('.')}"
            return FileResponse(f, media_type=media_type)
    raise HTTPException(status_code=404, detail="Audio not found")


@router.post("/voices")
async def list_voices(req: VoicesReq):
    """查询可用音色列表。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings)
    try:
        voices = await platform.list_voices(req.voice_type)
        return {"voices": [{"voiceId": v.voice_id, "name": v.name, "voiceType": v.voice_type} for v in voices]}
    except Exception as e:
        logger.exception("[TTS] list_voices error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


@router.post("/test-voices")
async def test_voices(req: TestVoicesReq):
    """使用临时 API 配置查询可用音色，供预设编辑器使用。"""
    _require_tts_enabled()
    platform = _get_inline_platform(req.baseUrl, req.apiKey)
    try:
        voices = await platform.list_voices(req.voice_type)
        return {"voices": [{"voiceId": v.voice_id, "name": v.name, "voiceType": v.voice_type} for v in voices]}
    except Exception as e:
        logger.exception("[TTS] test_voices error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


@router.post("/preprocess")
async def preprocess_text(req: PreprocessReq):
    """文本后处理：为 TTS 整理文本，可选注入 MiniMax 英文语气标签。"""
    settings = _require_tts_enabled()
    text = req.text.strip()
    if not text:
        return {"processedText": ""}

    base_url, api_key = _resolve_llm_credentials(
        settings,
        preset_id=req.preset_id,
        base_url=req.base_url,
        api_key=req.api_key,
    )

    lang_hint = (req.target_language or "").strip()
    system_prompt = (
        load_tts_post_process_prompt()
        .replace(
            "{{language}}",
            lang_hint if lang_hint else "not set — do not translate for language; only clean and normalize.",
        )
        .replace(
            "{{EMOTION_TAGS_DIRECTIVE}}",
            EMOTION_TAGS_DIRECTIVE if req.inject_emotion_tags else "Do not insert any emotion tags.",
        )
    )

    user_payload = json.dumps(
        {
            "language": lang_hint,
            "raw_text": text,
            "inject_emotion_tags": bool(req.inject_emotion_tags),
        },
        ensure_ascii=False,
    )

    try:
        result = await chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=req.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
        )
        payload = _parse_preprocess_json_payload(result.text)
        raw_out = payload.get("processed_text")
        if raw_out is None:
            raw_out = payload.get("processedText")
        processed = str(raw_out).strip() if raw_out is not None else ""
        if not processed:
            processed = text
        return {"processedText": processed}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.exception("[TTS] preprocess returned invalid json")
        raise HTTPException(status_code=502, detail=f"TTS preprocess invalid JSON response: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TTS] preprocess error")
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/design")
async def design_voice(req: DesignVoiceReq):
    """使用临时 API 配置执行音色设计，并返回试听地址。"""
    _require_tts_enabled()
    platform = _get_inline_platform(req.baseUrl, req.apiKey)
    try:
        result = await platform.design_voice(
            prompt=req.prompt,
            preview_text=req.preview_text,
            voice_id=req.voice_id,
            aigc_watermark=req.aigc_watermark,
        )
        preview_url = None
        if result.preview_audio_bytes:
            asset_id = _store_preview_audio(result.preview_audio_bytes, result.preview_format)
            preview_url = f"/api/tts/audio/{asset_id}"
        return {
            "voiceId": result.voice_id,
            "previewUrl": preview_url,
            "voiceType": "voice_generation",
        }
    except Exception as e:
        logger.exception("[TTS] design voice error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


@router.post("/clone")
async def clone_voice(
    baseUrl: str = Form(...),
    apiKey: str = Form(...),
    voice_id: str = Form(...),
    source_file: UploadFile = File(...),
    model: str | None = Form(None),
    text: str | None = Form(None),
    language_boost: str | None = Form(None),
    prompt_file: UploadFile | None = File(None),
    prompt_text: str | None = Form(None),
    need_noise_reduction: bool = Form(False),
    need_volume_normalization: bool = Form(False),
    aigc_watermark: bool = Form(False),
):
    """使用临时 API 配置执行音色快速复刻，并返回试听地址。"""
    _require_tts_enabled()
    platform = _get_inline_platform(baseUrl, apiKey)
    try:
        source_upload = await platform.upload_file(
            await source_file.read(),
            source_file.filename or "source-audio.wav",
            source_file.content_type,
        )
        prompt_audio_file_id = None
        if prompt_file is not None and prompt_text:
            prompt_upload = await platform.upload_file(
                await prompt_file.read(),
                prompt_file.filename or "prompt-audio.wav",
                prompt_file.content_type,
                purpose="prompt_audio",
            )
            prompt_audio_file_id = prompt_upload.file_id

        result = await platform.clone_voice(
            source_file_id=source_upload.file_id,
            voice_id=voice_id,
            model=model,
            text=text,
            language_boost=language_boost,
            prompt_audio_file_id=prompt_audio_file_id,
            prompt_text=prompt_text,
            need_noise_reduction=need_noise_reduction,
            need_volume_normalization=need_volume_normalization,
            aigc_watermark=aigc_watermark,
        )
        return {
            "voiceId": result.voice_id,
            "previewUrl": result.preview_url,
            "voiceType": "voice_cloning",
        }
    except Exception as e:
        logger.exception("[TTS] clone voice error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()
