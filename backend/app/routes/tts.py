"""
TTS 路由模块

提供语音合成、音色查询、缓存统计与清空等接口。
所有 /api/tts/* 路由在 ttsEnabled == false 时返回 403。
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.requests import Request
from pydantic import BaseModel, Field
import json

from app.assistant import load_tts_post_process_prompt
from app.llm.preset_resolve import (
    LlmPresetResolveError,
    is_llm_api_preset,
    resolve_llm_preset_credentials,
)
from app.llm.runtime import chat_completions
from app.llm.types import normalize_protocol_id
from app.schemas import Settings, TtsProvider
from app.services import glm_local_tts_process
from app.services import omnivoice_local_tts_process
from app.services import qwen3_local_tts_process
from app.services.tts_cache import tts_cache_patrol
from app.services.tts_platform import (
    GlmLocalTtsPlatform,
    GlmTtsPlatform,
    MiniMaxTtsPlatform,
    OmniVoiceLocalTtsPlatform,
    OpenAiSpeechCompatTtsPlatform,
    Qwen3LocalTtsPlatform,
    SynthesisRequest,
    SynthesisResult,
    TtsPlatform,
)
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
    "You may insert English speech tags in parentheses only when clearly justified by the text and only if the "
    "downstream TTS model is documented to support them; otherwise omit tags. "
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
            if preset.id == preset_id and preset.presetKind == "tts":
                return preset
        raise HTTPException(status_code=400, detail="指定的 TTS 预设不存在，或未标记为 TTS 服务")

    for preset in settings.apiPresets:
        if preset.presetKind == "tts":
            return preset

    raise HTTPException(status_code=400, detail="未配置 TTS API 预设（需在 API 预设中勾选 TTS 服务）")


def _resolve_tts_provider(raw: str | None) -> TtsProvider:
    normalized = (raw or "").strip().lower()
    if not normalized or normalized == "minimax":
        return "minimax"
    if normalized == "glm":
        return "glm"
    if normalized == "glm_local":
        return "glm_local"
    if normalized == "qwen3_local":
        return "qwen3_local"
    if normalized == "omnivoice_local":
        return "omnivoice_local"
    if normalized == "openrouter":
        return "openrouter"
    if normalized == "siliconflow":
        return "siliconflow"
    raise HTTPException(status_code=400, detail=f"不支持的 TTS provider: {raw}")


def _qwen3_voice_clone_port(matched: Any) -> int:
    main = matched.ttsQwen3LocalPort or 8080
    vc = matched.ttsQwen3LocalVoiceClonePort
    if vc is None:
        return main + 1
    return int(vc)


def _qwen3_voice_clone_base_url(matched: Any) -> str:
    vc_port = _qwen3_voice_clone_port(matched)
    raw = (matched.baseUrl or "").strip()
    if not raw or raw == "https://api.openai.com":
        return f"http://127.0.0.1:{vc_port}"
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or "127.0.0.1"
    scheme = parsed.scheme or "http"
    return urlunparse((scheme, f"{host}:{vc_port}", "", "", "", ""))


def _build_platform(
    *,
    base_url: str,
    api_key: str,
    provider: TtsProvider,
    voice_catalog: list[dict[str, Any]] | None = None,
    voice_clone_base_url: str | None = None,
) -> TtsPlatform:
    if provider == "glm_local":
        return GlmLocalTtsPlatform(
            base_url=base_url or "http://127.0.0.1:8088",
            voice_catalog=voice_catalog,
        )
    if provider == "qwen3_local":
        return Qwen3LocalTtsPlatform(
            base_url=base_url or "http://127.0.0.1:8080",
            voice_catalog=voice_catalog,
            voice_clone_base_url=voice_clone_base_url,
        )
    if provider == "omnivoice_local":
        return OmniVoiceLocalTtsPlatform(
            base_url=base_url or "http://127.0.0.1:8089",
            voice_catalog=voice_catalog,
        )
    if provider == "glm":
        return GlmTtsPlatform(api_key=api_key, base_url=base_url or "https://open.bigmodel.cn/api")
    if provider == "openrouter":
        return OpenAiSpeechCompatTtsPlatform(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
            variant="openrouter",
        )
    if provider == "siliconflow":
        return OpenAiSpeechCompatTtsPlatform(
            api_key=api_key,
            base_url=base_url or "https://api.siliconflow.cn/v1",
            variant="siliconflow",
        )
    return MiniMaxTtsPlatform(api_key=api_key, base_url=base_url or "https://api.minimaxi.com")


def _get_platform(settings: Settings, preset_id: str | None = None) -> TtsPlatform:
    """根据当前设置构建 TTS 平台实例。"""
    matched = _resolve_tts_preset(settings, preset_id)
    provider = _resolve_tts_provider(matched.ttsProvider)
    if provider not in {"glm_local", "qwen3_local", "omnivoice_local"} and not matched.apiKey:
        raise HTTPException(status_code=400, detail="TTS 预设缺少 API Key")
    voice_catalog = [v.model_dump(mode="json") for v in matched.voiceCatalog] if provider in {"glm_local", "qwen3_local", "omnivoice_local"} else None
    base_url = matched.baseUrl.strip()
    if provider == "glm_local" and not base_url:
        port = matched.ttsGlmLocalPort or 8088
        base_url = f"http://127.0.0.1:{port}"
    if provider == "qwen3_local" and (not base_url or base_url == "https://api.openai.com"):
        port = matched.ttsQwen3LocalPort or 8080
        base_url = f"http://127.0.0.1:{port}"
    if provider == "omnivoice_local" and not base_url:
        port = matched.ttsOmniVoiceLocalPort or 8089
        base_url = f"http://127.0.0.1:{port}"
    if provider == "openrouter" and (not base_url or base_url == "https://api.openai.com"):
        base_url = "https://openrouter.ai/api/v1"
    if provider == "siliconflow" and (not base_url or base_url == "https://api.openai.com"):
        base_url = "https://api.siliconflow.cn/v1"
    vc_url: str | None = None
    if provider == "qwen3_local":
        vc_url = _qwen3_voice_clone_base_url(matched)
    return _build_platform(
        base_url=base_url,
        api_key=(matched.apiKey or "").strip(),
        provider=provider,
        voice_catalog=voice_catalog,
        voice_clone_base_url=vc_url,
    )


def _get_inline_platform(base_url: str, api_key: str, provider: str | None) -> TtsPlatform:
    resolved_provider = _resolve_tts_provider(provider)
    if resolved_provider not in {"glm_local", "qwen3_local", "omnivoice_local"} and not api_key.strip():
        raise HTTPException(status_code=400, detail="TTS API Key 不能为空")
    return _build_platform(
        base_url=(base_url or "").strip(),
        api_key=(api_key or "").strip(),
        provider=resolved_provider,
        voice_clone_base_url=None,
    )


def _resolve_llm_credentials(
    settings: Settings,
    *,
    preset_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str, str]:
    """Resolve LLM credentials for TTS text preprocess. Returns (base_url, api_key, protocol)."""
    if api_key and api_key.strip():
        protocol = normalize_protocol_id(getattr(settings.llm, "protocol", None))
        if preset_id:
            matched = next((p for p in settings.apiPresets if p.id == preset_id), None)
            if matched is None:
                raise HTTPException(status_code=400, detail="后处理模型关联的 API 预设不存在")
            if not is_llm_api_preset(matched):
                raise HTTPException(status_code=400, detail="后处理模型不能使用 TTS 预设")
            protocol = normalize_protocol_id(getattr(matched, "protocol", None))
        return ((base_url or settings.llm.baseUrl).strip(), api_key.strip(), protocol)

    try:
        credentials = resolve_llm_preset_credentials(
            settings,
            explicit_preset_id=(preset_id or None),
        )
    except LlmPresetResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return credentials.base_url, credentials.api_key, credentials.protocol


def _write_asset_id_to_message(
    chat_id: str | None,
    message_id: str | None,
    asset_id: str,
    *,
    spoken_text: str | None = None,
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
        if spoken_text is not None:
            payload["ttsAudioSourceText"] = spoken_text
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
    provider: TtsProvider = "minimax"
    voice_type: str = "all"


class PreprocessReq(BaseModel):
    text: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    preset_id: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    provider: TtsProvider | None = None
    inject_emotion_tags: bool = False
    target_language: str | None = None


class DesignVoiceReq(BaseModel):
    baseUrl: str
    apiKey: str
    provider: TtsProvider = "minimax"
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


DISCONNECT_POLL_INTERVAL_S = 0.2


async def _synthesize_until_disconnect_or_cancel(
    request: Request,
    platform: TtsPlatform,
    synth_req: SynthesisRequest,
) -> SynthesisResult | None:
    """客户端断开时取消合成并关闭 platform；成功返回结果，否则返回 None。"""
    synth_task = asyncio.create_task(platform.synthesize(synth_req))

    async def wait_disconnect() -> None:
        while True:
            if await request.is_disconnected():
                return
            await asyncio.sleep(DISCONNECT_POLL_INTERVAL_S)

    disc_task = asyncio.create_task(wait_disconnect())

    done, _pending = await asyncio.wait(
        {synth_task, disc_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if disc_task in done:
        synth_task.cancel()
        try:
            await synth_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("[TTS] synthesize task after client disconnect", exc_info=True)
        await platform.close()
        return None

    disc_task.cancel()
    try:
        await disc_task
    except asyncio.CancelledError:
        pass

    return synth_task.result()


@router.post("/synthesize")
async def synthesize(request: Request, req: SynthesizeReq):
    """合成语音（非流式/流式）。"""
    settings = _require_tts_enabled()
    matched_preset = _resolve_tts_preset(settings, req.preset_id)
    provider = _resolve_tts_provider(matched_preset.ttsProvider)

    if provider == "glm_local" and matched_preset.ttsGlmLocalManaged:
        repo_path = (matched_preset.ttsGlmLocalRepoPath or "").strip()
        if not repo_path:
            raise HTTPException(status_code=400, detail="已启用托管启动，但未配置 GLM-TTS 仓库路径")
        port = matched_preset.ttsGlmLocalPort or 8088
        started = await glm_local_tts_process.start(repo_path, port)
        if not started:
            raise HTTPException(status_code=502, detail="GLM-TTS 本地托管启动失败，请检查仓库路径、模型依赖和端口配置")
    if provider == "qwen3_local" and matched_preset.ttsQwen3LocalManaged:
        repo_path = (matched_preset.ttsQwen3LocalRepoPath or "").strip()
        if not repo_path:
            raise HTTPException(status_code=400, detail="已启用托管启动，但未配置 Qwen3-TTS 仓库路径")
        main_port = matched_preset.ttsQwen3LocalPort or 8080
        vc_port = _qwen3_voice_clone_port(matched_preset)
        if vc_port == main_port:
            raise HTTPException(
                status_code=400,
                detail="Qwen3-TTS 语音克隆端口不能与主端口相同，请调整语音克隆端口或主端口（默认语音克隆为主端口+1）",
            )
        device = (matched_preset.ttsQwen3LocalDevice or "").strip() or "cuda:0"
        custom_model = (matched_preset.ttsQwen3LocalModelId or "").strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
        base_model = (matched_preset.ttsQwen3LocalBaseModelId or "").strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
        ok_custom = await qwen3_local_tts_process.start(
            repo_path,
            main_port,
            model_id=custom_model,
            device=device,
        )
        ok_base = await qwen3_local_tts_process.start(
            repo_path,
            vc_port,
            model_id=base_model,
            device=device,
        )
        if not (ok_custom and ok_base):
            raise HTTPException(status_code=502, detail="Qwen3-TTS 本地托管启动失败，请检查仓库路径、模型依赖和端口配置")
    if provider == "omnivoice_local" and matched_preset.ttsOmniVoiceLocalManaged:
        repo_path = (matched_preset.ttsOmniVoiceLocalRepoPath or "").strip()
        if not repo_path:
            raise HTTPException(status_code=400, detail="已启用托管启动，但未配置 OmniVoice 仓库路径")
        port = matched_preset.ttsOmniVoiceLocalPort or 8089
        started = await omnivoice_local_tts_process.start(
            repo_path,
            port,
            model_id=(matched_preset.ttsOmniVoiceLocalModelId or "").strip() or "k2-fsa/OmniVoice",
            device=(matched_preset.ttsOmniVoiceLocalDevice or "").strip(),
        )
        if not started:
            raise HTTPException(status_code=502, detail="OmniVoice 本地托管启动失败，请检查仓库路径、模型依赖和端口配置")

    platform = _get_platform(settings, req.preset_id)

    extra: dict[str, Any] = {}
    if provider == "glm_local":
        # 从 voiceCatalog 解析参考音频与转写文本
        voice_entry = next(
            (v for v in matched_preset.voiceCatalog if v.voiceId == req.voice_id),
            None,
        )
        if not voice_entry:
            raise HTTPException(
                status_code=400,
                detail=f"voice_id '{req.voice_id}' 未在预设音色目录中找到，请先在预设中添加该本地参考音色。",
            )
        extra["prompt_text"] = voice_entry.promptText or ""
        extra["prompt_audio_path"] = voice_entry.promptAudioPath or ""
        extra["sample_rate"] = req.sample_rate or 24000
    elif provider == "qwen3_local":
        voice_entry = next(
            (v for v in matched_preset.voiceCatalog if v.voiceId == req.voice_id),
            None,
        )
        extra["language"] = (matched_preset.ttsQwen3LocalDefaultLanguage or "Auto").strip() or "Auto"
        extra["instruction"] = (voice_entry.instruction or "").strip() if voice_entry else ""
        extra["prompt_text"] = (voice_entry.promptText or "").strip() if voice_entry else ""
        extra["prompt_audio_path"] = (voice_entry.promptAudioPath or "").strip() if voice_entry else ""
    elif provider == "omnivoice_local":
        voice_entry = next(
            (v for v in matched_preset.voiceCatalog if v.voiceId == req.voice_id),
            None,
        )
        if not voice_entry:
            raise HTTPException(
                status_code=400,
                detail=f"voice_id '{req.voice_id}' 未在预设音色目录中找到，请先在预设中添加该 OmniVoice 音色条目。",
            )
        extra["language"] = (matched_preset.ttsOmniVoiceLocalDefaultLanguage or "").strip()
        extra["instruction"] = (voice_entry.instruction or "").strip()
        extra["prompt_text"] = (voice_entry.promptText or "").strip()
        extra["prompt_audio_path"] = (voice_entry.promptAudioPath or "").strip()

    synth_req = SynthesisRequest(
        text=req.text,
        voice_id=req.voice_id,
        model=req.model,
        speed=req.speed,
        volume=req.volume,
        pitch=req.pitch,
        emotion=req.emotion,
        audio_format="wav" if provider in {"glm_local", "qwen3_local", "omnivoice_local"} else req.audio_format,
        sample_rate=req.sample_rate,
        stream=req.stream,
        extra=extra,
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
            result = await _synthesize_until_disconnect_or_cancel(request, platform, synth_req)
            if result is None:
                return Response(status_code=499)
            await platform.close()

            # 写入缓存文件
            asset_id = uuid4().hex
            cache_dir = get_tts_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            ext = result.format or "mp3"
            cache_path = cache_dir / f"{asset_id}.{ext}"
            cache_path.write_bytes(result.audio_bytes)
            # 前端流式阶段仍使用 local_* 临时 id，磁盘消息为服务端 UUID，写回必失败；由 bind-message 补绑
            mid = (req.message_id or "").strip()
            if mid and not mid.startswith("local_"):
                _write_asset_id_to_message(
                    req.chat_id,
                    req.message_id,
                    asset_id,
                    spoken_text=req.text,
                )

            return {
                "assetId": asset_id,
                "format": result.format,
                "sampleRate": result.sample_rate,
                "sizeBytes": len(result.audio_bytes),
                "warnings": list(getattr(result, "warnings", ()) or ()),
                "partialSuccess": bool(getattr(result, "warnings", ()) or ()),
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TTS] synthesize error")
        await platform.close()
        raise HTTPException(status_code=502, detail=str(e))


class BindMessageReq(BaseModel):
    chat_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    spoken_text: str | None = None


@router.post("/bind-message")
def bind_tts_asset_to_message(req: BindMessageReq):
    """将已合成的 TTS 资产绑定到服务端消息（补写 ttsAudioAssetId / ttsAudioSourceText）。"""
    _require_tts_enabled()
    # 校验 asset_id 格式
    if not req.asset_id.isalnum() or len(req.asset_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid asset ID")
    _write_asset_id_to_message(
        req.chat_id,
        req.message_id,
        req.asset_id,
        spoken_text=req.spoken_text,
    )
    return {"ok": True}


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
        detailed = await platform.list_voices_detailed(req.voice_type)
        return {
            "voices": [
                {"voiceId": v.voice_id, "name": v.name, "voiceType": v.voice_type}
                for v in detailed.voices
            ],
            "warnings": list(detailed.warnings),
            "partialSuccess": bool(detailed.partial_success),
        }
    except Exception as e:
        logger.exception("[TTS] list_voices error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


@router.post("/test-voices")
async def test_voices(req: TestVoicesReq):
    """使用临时 API 配置查询可用音色，供预设编辑器使用。"""
    _require_tts_enabled()
    resolved_provider = _resolve_tts_provider(req.provider)
    if resolved_provider == "glm_local":
        return {"voices": [], "hint": "GLM-TTS（本地）无远程音色列表，请在预设中手动添加参考音色。"}
    if resolved_provider == "qwen3_local":
        return {"voices": [], "hint": "Qwen3-TTS（本地）当前走 FastAPI 网关；请在预设中手动维护 speaker 名称，或直接查网关的 /v1/meta。"}
    if resolved_provider == "omnivoice_local":
        return {"voices": [], "hint": "OmniVoice（本地）采用预设内音色目录；请手动维护“自动 / 指令 / 克隆”音色条目。"}
    if resolved_provider == "openrouter":
        return {
            "voices": [],
            "hint": "OpenRouter TTS 无统一音色列表接口；请在预设「音色目录」中填写 voice，或在 openrouter.ai 查看模型说明。",
        }
    platform = _get_inline_platform(req.baseUrl, req.apiKey, req.provider)
    try:
        detailed = await platform.list_voices_detailed(req.voice_type)
        return {
            "voices": [
                {"voiceId": v.voice_id, "name": v.name, "voiceType": v.voice_type}
                for v in detailed.voices
            ],
            "warnings": list(detailed.warnings),
            "partialSuccess": bool(detailed.partial_success),
        }
    except Exception as e:
        logger.exception("[TTS] test_voices error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


class GlmLocalActionReq(BaseModel):
    preset_id: str | None = None


@router.post("/glm-local/health")
async def glm_local_health(req: GlmLocalActionReq):
    """检查 GLM-TTS 本地服务是否就绪。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings, req.preset_id)
    if not isinstance(platform, GlmLocalTtsPlatform):
        raise HTTPException(status_code=400, detail="当前预设不是 GLM-TTS（本地）提供商")
    try:
        detail = await platform.health_check_detail()
        process_health = glm_local_tts_process.get_health()
        reachable = bool(detail.get("ok"))
        # 服务已可达时以探测结果为准，不把历史 process 失败态合并到顶层 code/lastError
        if reachable:
            matched = _resolve_tts_preset(settings, req.preset_id)
            glm_local_tts_process.note_reachable(port=matched.ttsGlmLocalPort or 8088)
            process_health = glm_local_tts_process.get_health()
            return {
                "ok": True,
                "health": {
                    "reachable": True,
                    "code": None,
                    "lastError": None,
                    "process": process_health,
                },
            }
        return {
            "ok": False,
            "health": {
                "reachable": False,
                "code": detail.get("code") or process_health.get("code"),
                "lastError": detail.get("lastError") or process_health.get("lastError"),
                "process": process_health,
            },
        }
    finally:
        await platform.close()


@router.post("/glm-local/clear-vram")
async def glm_local_clear_vram(req: GlmLocalActionReq):
    """调用本地 GLM-TTS 的 clear_vram 接口释放显存。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings, req.preset_id)
    if not isinstance(platform, GlmLocalTtsPlatform):
        raise HTTPException(status_code=400, detail="当前预设不是 GLM-TTS（本地）提供商")
    try:
        ok = await platform.clear_vram()
        return {"ok": ok}
    finally:
        await platform.close()


class GlmLocalStartReq(BaseModel):
    preset_id: str | None = None


@router.post("/glm-local/start")
async def glm_local_start(req: GlmLocalStartReq):
    """启动托管的 GLM-TTS 本地子进程。"""
    settings = _require_tts_enabled()
    matched = _resolve_tts_preset(settings, req.preset_id)
    provider = _resolve_tts_provider(matched.ttsProvider)
    if provider != "glm_local":
        raise HTTPException(status_code=400, detail="当前预设不是 GLM-TTS（本地）提供商")
    if not matched.ttsGlmLocalManaged:
        raise HTTPException(status_code=400, detail="该预设未启用托管启动")
    repo_path = (matched.ttsGlmLocalRepoPath or "").strip()
    if not repo_path:
        raise HTTPException(status_code=400, detail="未配置 GLM-TTS 仓库路径")
    port = matched.ttsGlmLocalPort or 8088
    ok = await glm_local_tts_process.start(repo_path, port)
    health = glm_local_tts_process.get_health()
    return {"ok": ok, "health": health}


class Qwen3LocalActionReq(BaseModel):
    preset_id: str | None = None


@router.post("/qwen3-local/health")
async def qwen3_local_health(req: Qwen3LocalActionReq):
    """检查 Qwen3-TTS 本地服务是否就绪。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings, req.preset_id)
    if not isinstance(platform, Qwen3LocalTtsPlatform):
        raise HTTPException(status_code=400, detail="当前预设不是 Qwen3-TTS（本地）提供商")
    try:
        ok = await platform.health_check()
        return {"ok": ok}
    finally:
        await platform.close()


class Qwen3LocalStartReq(BaseModel):
    preset_id: str | None = None


@router.post("/qwen3-local/start")
async def qwen3_local_start(req: Qwen3LocalStartReq):
    """启动托管的 Qwen3-TTS 本地子进程。"""
    settings = _require_tts_enabled()
    matched = _resolve_tts_preset(settings, req.preset_id)
    provider = _resolve_tts_provider(matched.ttsProvider)
    if provider != "qwen3_local":
        raise HTTPException(status_code=400, detail="当前预设不是 Qwen3-TTS（本地）提供商")
    if not matched.ttsQwen3LocalManaged:
        raise HTTPException(status_code=400, detail="该预设未启用托管启动")
    repo_path = (matched.ttsQwen3LocalRepoPath or "").strip()
    if not repo_path:
        raise HTTPException(status_code=400, detail="未配置 Qwen3-TTS 仓库路径")
    main_port = matched.ttsQwen3LocalPort or 8080
    vc_port = _qwen3_voice_clone_port(matched)
    if vc_port == main_port:
        raise HTTPException(
            status_code=400,
            detail="Qwen3-TTS 语音克隆端口不能与主端口相同，请调整语音克隆端口或主端口（默认语音克隆为主端口+1）",
        )
    device = (matched.ttsQwen3LocalDevice or "").strip() or "cuda:0"
    custom_model = (matched.ttsQwen3LocalModelId or "").strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    base_model = (matched.ttsQwen3LocalBaseModelId or "").strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    ok_custom = await qwen3_local_tts_process.start(
        repo_path,
        main_port,
        model_id=custom_model,
        device=device,
    )
    ok_base = await qwen3_local_tts_process.start(
        repo_path,
        vc_port,
        model_id=base_model,
        device=device,
    )
    return {"ok": ok_custom and ok_base}


class OmniVoiceLocalActionReq(BaseModel):
    preset_id: str | None = None


@router.post("/omnivoice-local/health")
async def omnivoice_local_health(req: OmniVoiceLocalActionReq):
    """检查 OmniVoice 本地服务是否就绪。"""
    settings = _require_tts_enabled()
    platform = _get_platform(settings, req.preset_id)
    if not isinstance(platform, OmniVoiceLocalTtsPlatform):
        raise HTTPException(status_code=400, detail="当前预设不是 OmniVoice（本地）提供商")
    try:
        ok = await platform.health_check()
        return {"ok": ok}
    finally:
        await platform.close()


class OmniVoiceLocalStartReq(BaseModel):
    preset_id: str | None = None


@router.post("/omnivoice-local/start")
async def omnivoice_local_start(req: OmniVoiceLocalStartReq):
    """启动托管的 OmniVoice 本地子进程。"""
    settings = _require_tts_enabled()
    matched = _resolve_tts_preset(settings, req.preset_id)
    provider = _resolve_tts_provider(matched.ttsProvider)
    if provider != "omnivoice_local":
        raise HTTPException(status_code=400, detail="当前预设不是 OmniVoice（本地）提供商")
    if not matched.ttsOmniVoiceLocalManaged:
        raise HTTPException(status_code=400, detail="该预设未启用托管启动")
    repo_path = (matched.ttsOmniVoiceLocalRepoPath or "").strip()
    if not repo_path:
        raise HTTPException(status_code=400, detail="未配置 OmniVoice 仓库路径")
    port = matched.ttsOmniVoiceLocalPort or 8089
    ok = await omnivoice_local_tts_process.start(
        repo_path,
        port,
        model_id=(matched.ttsOmniVoiceLocalModelId or "").strip() or "k2-fsa/OmniVoice",
        device=(matched.ttsOmniVoiceLocalDevice or "").strip(),
    )
    return {"ok": ok}


@router.post("/preprocess")
async def preprocess_text(req: PreprocessReq):
    """文本后处理：为 TTS 整理文本，可选注入兼容标签。"""
    settings = _require_tts_enabled()
    text = req.text.strip()
    if not text:
        return {"processedText": ""}

    base_url, api_key, protocol = _resolve_llm_credentials(
        settings,
        preset_id=req.preset_id,
        base_url=req.base_url,
        api_key=req.api_key,
    )

    provider = _resolve_tts_provider(req.provider)
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
            protocol=protocol,
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
    platform = _get_inline_platform(req.baseUrl, req.apiKey, req.provider)
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
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.exception("[TTS] design voice error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()


@router.post("/clone")
async def clone_voice(
    baseUrl: str = Form(...),
    apiKey: str = Form(...),
    provider: str = Form("minimax"),
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
    resolved_provider = _resolve_tts_provider(provider)
    platform = _get_inline_platform(baseUrl, apiKey, resolved_provider)
    try:
        if resolved_provider == "siliconflow":
            source_bytes = await source_file.read()
            transcript = (text or "").strip()
            if not transcript:
                raise HTTPException(
                    status_code=400,
                    detail="硅基流动参考音频上传必须填写参考音频对应文本（表单字段 text）",
                )
            result = await platform.upload_reference_voice(
                file_bytes=source_bytes,
                filename=source_file.filename or "audio.mp3",
                content_type=source_file.content_type,
                model=(model or "").strip() or "FunAudioLLM/CosyVoice2-0.5B",
                custom_name=voice_id.strip(),
                text=transcript,
            )
            return {
                "voiceId": result.voice_id,
                "previewUrl": result.preview_url,
                "voiceType": "private",
            }
        source_upload = await platform.upload_file(
            await source_file.read(),
            source_file.filename or "source-audio.wav",
            source_file.content_type,
        )
        prompt_audio_file_id = None
        if resolved_provider == "minimax" and prompt_file is not None and prompt_text:
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
            "voiceType": "private" if resolved_provider == "glm" else "voice_cloning",
        }
    except Exception as e:
        logger.exception("[TTS] clone voice error")
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await platform.close()
