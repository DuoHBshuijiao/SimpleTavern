"""
TTS 平台抽象层

定义 TtsPlatform 接口以及 MiniMax / GLM TTS 实现。
其他厂商可继续继承 TtsPlatform 扩展。
"""

from __future__ import annotations

import abc
import base64
import io
import json
import logging
import mimetypes
import pathlib
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
import wave

import httpx

from app.llm.openai_compat import _normalize_base_url

logger = logging.getLogger(__name__)


def _normalize_minimax_api_base(raw: str) -> str:
    """
    与 LLM 预设一致：支持仅域名、…/v1、…/v1/，或含 /chat/completions 的完整地址；
    规范化后作为 httpx base_url（已含单一路径前缀 /v1），后续请求路径不要再带 /v1。
    """
    base = raw.strip()
    if base and not (base.startswith("http://") or base.startswith("https://")):
        base = "https://" + base
    base = base.rstrip("/")
    low = base.lower()
    if "/chat/completions" in low:
        idx = low.find("/chat/completions")
        base = base[:idx].rstrip("/")
    return _normalize_base_url(base)


def _normalize_glm_api_base(raw: str) -> str:
    """
    规范化智谱 TTS Base URL。

    支持：
    - 域名本身：open.bigmodel.cn
    - API 根路径：https://open.bigmodel.cn/api
    - 完整接口路径：.../api/paas/v4/audio/speech 等
    """
    base = (raw or "https://open.bigmodel.cn/api").strip()
    if not base:
        base = "https://open.bigmodel.cn/api"
    if not (base.startswith("http://") or base.startswith("https://")):
        base = "https://" + base
    base = base.rstrip("/")
    low = base.lower()
    for marker in (
        "/paas/v4/audio/speech",
        "/paas/v4/voice/list",
        "/paas/v4/voice/clone",
        "/paas/v4/files",
    ):
        idx = low.find(marker)
        if idx >= 0:
            base = base[:idx].rstrip("/")
            low = base.lower()
            break
    if low.endswith("/paas/v4"):
        base = base[: -len("/paas/v4")].rstrip("/")
        low = base.lower()
    if not low.endswith("/api"):
        base = base + "/api"
    return base


def _normalize_local_http_base(raw: str, default: str) -> str:
    base = (raw or default).strip()
    if not base:
        base = default
    if not (base.startswith("http://") or base.startswith("https://")):
        base = "http://" + base
    return base.rstrip("/")


def _guess_wav_sample_rate(audio_bytes: bytes, fallback: int) -> int:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            return int(wav_file.getframerate())
    except Exception:
        return fallback

# ---------------------------------------------------------------------------
# 通用数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VoiceInfo:
    voice_id: str
    name: str
    voice_type: str  # system | voice_cloning | voice_generation
    preview_url: str | None = None


@dataclass(frozen=True)
class SynthesisResult:
    """合成结果（非流式）。"""
    audio_bytes: bytes
    format: str  # mp3, wav, flac, pcm
    sample_rate: int


@dataclass
class SynthesisRequest:
    """合成请求参数（平台无关）。"""
    text: str
    voice_id: str
    model: str = "speech-2.8-hd"
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0
    emotion: str | None = None
    audio_format: str = "mp3"
    sample_rate: int = 32000
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceCloneResult:
    voice_id: str
    preview_url: str | None = None


@dataclass(frozen=True)
class VoiceDesignResult:
    voice_id: str
    preview_audio_bytes: bytes | None = None
    preview_format: str = "mp3"


@dataclass(frozen=True)
class UploadFileResult:
    file_id: str


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class TtsPlatform(abc.ABC):
    """TTS 平台适配器抽象接口。"""

    @abc.abstractmethod
    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        """非流式合成，返回完整音频。"""

    @abc.abstractmethod
    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        """流式合成，逐 chunk 返回音频字节。"""

    @abc.abstractmethod
    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        """查询可用音色列表。"""

    @abc.abstractmethod
    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        *,
        purpose: str = "voice_clone",
    ) -> UploadFileResult:
        """上传音频文件，返回平台 file_id。MiniMax 要求主复刻音频与 clone_prompt 示例音频使用不同 purpose。"""

    @abc.abstractmethod
    async def clone_voice(
        self,
        *,
        source_file_id: str,
        voice_id: str,
        model: str | None = None,
        text: str | None = None,
        language_boost: str | None = None,
        prompt_audio_file_id: str | None = None,
        prompt_text: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        """快速复刻音色。"""

    @abc.abstractmethod
    async def design_voice(
        self,
        *,
        prompt: str,
        preview_text: str,
        voice_id: str | None = None,
        aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        """音色设计并返回试听音频。"""

    async def close(self) -> None:
        """清理资源（如 HTTP 连接池）。"""


# ---------------------------------------------------------------------------
# MiniMax 实现
# ---------------------------------------------------------------------------

_MINIMAX_BASE = "https://api.minimaxi.com"


class MiniMaxTtsPlatform(TtsPlatform):
    """MiniMax 语音合成适配器（同步/流式 + 音色查询）。"""

    def __init__(self, api_key: str, base_url: str = _MINIMAX_BASE) -> None:
        self._api_key = api_key
        self._base_url = _normalize_minimax_api_base(base_url or _MINIMAX_BASE)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ---- 合成 (非流式) ----

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        body = self._build_t2a_body(req, stream=False)
        resp = await self._client.post("/t2a_v2", json=body, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        audio_hex: str = data.get("data", {}).get("audio", "")
        if not audio_hex:
            raise RuntimeError("MiniMax 返回空音频数据")
        return SynthesisResult(
            audio_bytes=bytes.fromhex(audio_hex),
            format=req.audio_format,
            sample_rate=req.sample_rate,
        )

    # ---- 合成 (流式) ----

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        body = self._build_t2a_body(req, stream=True)
        async with self._client.stream(
            "POST", "/t2a_v2", json=body, headers=self._headers()
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                # SSE: data: {...}
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                import json as _json
                try:
                    chunk = _json.loads(line)
                except Exception:
                    continue
                audio_hex = chunk.get("data", {}).get("audio", "")
                if audio_hex:
                    yield bytes.fromhex(audio_hex)

    # ---- 音色列表 ----

    @staticmethod
    def _voice_display_name(item: dict[str, Any]) -> str:
        """MiniMax get_voice：系统音色用 voice_name，其余可用 description 首条或回退 voice_id。"""
        vid = str(item.get("voice_id") or "").strip()
        name = item.get("voice_name") or item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        desc = item.get("description")
        if isinstance(desc, list) and desc:
            first = desc[0]
            if isinstance(first, str) and first.strip():
                return first.strip()[:200]
        return vid

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        body = {"voice_type": voice_type}
        resp = await self._client.post("/get_voice", json=body, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        voices: list[VoiceInfo] = []

        inner = data.get("data") if isinstance(data.get("data"), dict) else None

        def _arr(key: str) -> list[Any]:
            raw = data.get(key)
            if raw is None and inner is not None:
                raw = inner.get(key)
            return raw if isinstance(raw, list) else []

        # 官方 OpenAPI：system_voice / voice_cloning / voice_generation（无 voice_list）
        for item in _arr("system_voice"):
            if not isinstance(item, dict):
                continue
            vid = str(item.get("voice_id") or "").strip()
            if not vid:
                continue
            voices.append(
                VoiceInfo(
                    voice_id=vid,
                    name=self._voice_display_name(item) or vid,
                    voice_type="system",
                )
            )
        for item in _arr("voice_cloning"):
            if not isinstance(item, dict):
                continue
            vid = str(item.get("voice_id") or "").strip()
            if not vid:
                continue
            voices.append(
                VoiceInfo(
                    voice_id=vid,
                    name=self._voice_display_name(item) or vid,
                    voice_type="voice_cloning",
                )
            )
        for item in _arr("voice_generation"):
            if not isinstance(item, dict):
                continue
            vid = str(item.get("voice_id") or "").strip()
            if not vid:
                continue
            voices.append(
                VoiceInfo(
                    voice_id=vid,
                    name=self._voice_display_name(item) or vid,
                    voice_type="voice_generation",
                )
            )

        # 兼容旧字段名 voice_list（若上游曾返回扁平列表）
        if not voices:
            legacy = data.get("voice_list") or (inner or {}).get("voice_list") or []
            for item in legacy:
                if not isinstance(item, dict):
                    continue
                vid = str(item.get("voice_id") or "").strip()
                if not vid:
                    continue
                vtype = str(item.get("voice_type") or "system").strip() or "system"
                voices.append(
                    VoiceInfo(
                        voice_id=vid,
                        name=self._voice_display_name(item) or item.get("name") or vid,
                        voice_type=vtype,
                    )
                )

        return voices

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        *,
        purpose: str = "voice_clone",
    ) -> UploadFileResult:
        file_content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.post(
            "/files/upload",
            headers=headers,
            data={"purpose": purpose},
            files={"file": (filename, file_bytes, file_content_type)},
        )
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        file_id = data.get("file", {}).get("file_id") or data.get("file_id") or data.get("data", {}).get("file_id")
        if file_id is None:
            raise RuntimeError("MiniMax 文件上传未返回 file_id")
        return UploadFileResult(file_id=str(file_id))

    async def clone_voice(
        self,
        *,
        source_file_id: str,
        voice_id: str,
        model: str | None = None,
        text: str | None = None,
        language_boost: str | None = None,
        prompt_audio_file_id: str | None = None,
        prompt_text: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        body: dict[str, Any] = {
            "file_id": int(source_file_id),
            "voice_id": voice_id,
            "need_noise_reduction": need_noise_reduction,
            "need_volume_normalization": need_volume_normalization,
            "aigc_watermark": aigc_watermark,
        }
        if text:
            body["text"] = text[:1000]
        if model:
            body["model"] = model
        if language_boost:
            body["language_boost"] = language_boost
        if prompt_audio_file_id and prompt_text:
            body["clone_prompt"] = {
                "prompt_audio": int(prompt_audio_file_id),
                "prompt_text": prompt_text,
            }

        resp = await self._client.post("/voice_clone", json=body, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        preview_url = data.get("demo_audio") or data.get("data", {}).get("demo_audio")
        return VoiceCloneResult(voice_id=voice_id, preview_url=preview_url)

    async def design_voice(
        self,
        *,
        prompt: str,
        preview_text: str,
        voice_id: str | None = None,
        aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        body: dict[str, Any] = {
            "prompt": prompt,
            "preview_text": preview_text[:500],
            "aigc_watermark": aigc_watermark,
        }
        if voice_id:
            body["voice_id"] = voice_id

        resp = await self._client.post("/voice_design", json=body, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._check_base_resp(data)
        resolved_voice_id = data.get("voice_id") or data.get("data", {}).get("voice_id") or voice_id
        if not resolved_voice_id:
            raise RuntimeError("MiniMax 音色设计未返回 voice_id")
        audio_hex = data.get("trial_audio") or data.get("data", {}).get("trial_audio") or ""
        audio_bytes = bytes.fromhex(audio_hex) if audio_hex else None
        return VoiceDesignResult(
            voice_id=resolved_voice_id,
            preview_audio_bytes=audio_bytes,
            preview_format="mp3",
        )

    # ---- 内部工具 ----

    @staticmethod
    def _build_t2a_body(req: SynthesisRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": req.model,
            "text": req.text[:10000],  # MiniMax 限制 10000 字符
            "stream": stream,
            "voice_setting": {
                "voice_id": req.voice_id,
                "speed": max(0.5, min(2.0, req.speed)),
                "vol": max(0.01, min(10.0, req.volume)),
                "pitch": max(-12, min(12, req.pitch)),
            },
            "audio_setting": {
                "sample_rate": req.sample_rate,
                "format": req.audio_format,
            },
        }
        if req.emotion:
            body["voice_setting"]["emotion"] = req.emotion
        # 流式强制 mp3（MiniMax 约束：流式不支持 wav）
        if stream and req.audio_format == "wav":
            body["audio_setting"]["format"] = "mp3"
        # 合并 extra 字段（pronunciation_dict、timbre_weights 等）
        for k, v in req.extra.items():
            if k not in body:
                body[k] = v
        return body

    @staticmethod
    def _check_base_resp(data: dict[str, Any]) -> None:
        base_resp = data.get("base_resp", {})
        code = base_resp.get("status_code", 0)
        if code != 0:
            msg = base_resp.get("status_msg", f"MiniMax error code={code}")
            raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# GLM 实现
# ---------------------------------------------------------------------------

_GLM_BASE = "https://open.bigmodel.cn/api"


class GlmTtsPlatform(TtsPlatform):
    """智谱 GLM TTS 适配器。"""

    def __init__(self, api_key: str, base_url: str = _GLM_BASE) -> None:
        self._api_key = api_key
        self._base_url = _normalize_glm_api_base(base_url or _GLM_BASE)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=10, read=120, write=60, pool=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _json_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_error_message(data: Any) -> str | None:
        if not isinstance(data, dict):
            return None
        err = data.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            code = err.get("code")
            if message and code:
                return f"{message} (code={code})"
            if message:
                return str(message)
        return None

    @classmethod
    def _raise_for_http_error(cls, resp: httpx.Response) -> None:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = None
            try:
                detail = cls._extract_error_message(resp.json())
            except Exception:
                detail = None
            if detail:
                raise RuntimeError(detail) from exc
            raise

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = await self._client.request(method, path, **kwargs)
        self._raise_for_http_error(resp)
        data = resp.json()
        detail = self._extract_error_message(data)
        if detail:
            raise RuntimeError(detail)
        if not isinstance(data, dict):
            raise RuntimeError("GLM TTS 返回了非 JSON 对象")
        return data

    @staticmethod
    def _clamp_text(text: str, *, max_length: int = 1024) -> str:
        if len(text) <= max_length:
            return text
        logger.warning("[TTS] GLM input truncated", extra={"original_length": len(text), "max_length": max_length})
        return text[:max_length]

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        body = {
            "model": (req.model or "glm-tts").strip() or "glm-tts",
            "input": self._clamp_text(req.text),
            "voice": req.voice_id,
            "response_format": "wav",
            "speed": max(0.5, min(2.0, req.speed)),
            "volume": max(0.01, min(10.0, req.volume)),
        }
        resp = await self._client.post("/paas/v4/audio/speech", json=body, headers=self._json_headers())
        self._raise_for_http_error(resp)
        return SynthesisResult(
            audio_bytes=resp.content,
            format="wav",
            sample_rate=24000,
        )

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        body = {
            "model": (req.model or "glm-tts").strip() or "glm-tts",
            "input": self._clamp_text(req.text),
            "voice": req.voice_id,
            "stream": True,
            "response_format": "pcm",
            "encode_format": "base64",
            "speed": max(0.5, min(2.0, req.speed)),
            "volume": max(0.01, min(10.0, req.volume)),
        }
        async with self._client.stream(
            "POST",
            "/paas/v4/audio/speech",
            json=body,
            headers=self._json_headers(),
        ) as resp:
            self._raise_for_http_error(resp)
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                detail = self._extract_error_message(chunk)
                if detail:
                    raise RuntimeError(detail)
                for choice in chunk.get("choices") or []:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield base64.b64decode(content)

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        params: dict[str, str] = {}
        normalized = (voice_type or "all").strip().lower()
        if normalized == "system":
            params["voiceType"] = "OFFICIAL"
        elif normalized in {"voice_cloning", "voice_generation"}:
            params["voiceType"] = "PRIVATE"
        data = await self._request_json(
            "GET",
            "/paas/v4/voice/list",
            params=params,
            headers=self._auth_headers(),
        )
        voices: list[VoiceInfo] = []
        for item in data.get("voice_list") or []:
            if not isinstance(item, dict):
                continue
            voice_id = str(item.get("voice") or "").strip()
            if not voice_id:
                continue
            raw_type = str(item.get("voice_type") or "OFFICIAL").strip().lower() or "official"
            name = str(item.get("voice_name") or voice_id).strip() or voice_id
            preview_url = item.get("download_url") if isinstance(item.get("download_url"), str) else None
            voices.append(
                VoiceInfo(
                    voice_id=voice_id,
                    name=name,
                    voice_type=raw_type,
                    preview_url=preview_url,
                )
            )
        return voices

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        *,
        purpose: str = "voice_clone",
    ) -> UploadFileResult:
        del purpose
        file_content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = await self._request_json(
            "POST",
            "/paas/v4/files",
            headers=self._auth_headers(),
            data={"purpose": "voice-clone-input"},
            files={"file": (filename, file_bytes, file_content_type)},
        )
        file_id = data.get("id")
        if not isinstance(file_id, str) or not file_id.strip():
            raise RuntimeError("GLM 文件上传未返回 id")
        return UploadFileResult(file_id=file_id.strip())

    async def clone_voice(
        self,
        *,
        source_file_id: str,
        voice_id: str,
        model: str | None = None,
        text: str | None = None,
        language_boost: str | None = None,
        prompt_audio_file_id: str | None = None,
        prompt_text: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        del language_boost, prompt_audio_file_id, need_noise_reduction, need_volume_normalization, aigc_watermark
        preview_text = (text or "你好，这是音色试听。")[:1024]
        body: dict[str, Any] = {
            "model": (model or "glm-tts-clone").strip() or "glm-tts-clone",
            "voice_name": voice_id,
            "input": preview_text,
            "file_id": source_file_id,
        }
        if prompt_text:
            body["text"] = prompt_text[:1000]
        data = await self._request_json(
            "POST",
            "/paas/v4/voice/clone",
            json=body,
            headers=self._json_headers(),
        )
        resolved_voice_id = str(data.get("voice") or voice_id).strip() or voice_id
        preview_url = None
        try:
            for voice in await self.list_voices("all"):
                if voice.voice_id == resolved_voice_id and voice.preview_url:
                    preview_url = voice.preview_url
                    break
        except Exception:
            logger.warning("[TTS] GLM clone preview lookup failed", extra={"voice_id": resolved_voice_id}, exc_info=True)
        return VoiceCloneResult(voice_id=resolved_voice_id, preview_url=preview_url)

    async def design_voice(
        self,
        *,
        prompt: str,
        preview_text: str,
        voice_id: str | None = None,
        aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        del prompt, preview_text, voice_id, aigc_watermark
        raise NotImplementedError("GLM TTS 暂不支持音色设计")


# ---------------------------------------------------------------------------
# GLM-TTS 本地实现
# ---------------------------------------------------------------------------


class GlmLocalTtsPlatform(TtsPlatform):
    """
    GLM-TTS 本地 API 适配器。

    对接 ``tools/api_server.py`` （FastAPI），默认 ``http://127.0.0.1:8088``。
    优先使用 ``POST /api/v1/tts/json``（同机 Base64 响应，避免重复上传大文件）；
    若 ``prompt_audio_path`` 无效则回退 ``POST /api/v1/tts``（multipart）。
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8088",
        voice_catalog: list[dict[str, Any]] | None = None,
    ) -> None:
        url = (base_url or "http://127.0.0.1:8088").strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "http://" + url
        self._base_url = url
        self._voice_catalog = voice_catalog or []
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=15, read=600, write=60, pool=15),
        )

    async def close(self) -> None:
        await self._client.aclose()

    # -- synthesize --------------------------------------------------------

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        text = req.text.strip()
        if not text:
            raise ValueError("input_text 不能为空")

        prompt_text: str = (req.extra.get("prompt_text", "") or "").strip()
        prompt_audio_path: str = (req.extra.get("prompt_audio_path", "") or "").strip()
        sample_rate: int = req.extra.get("sample_rate", req.sample_rate) or 24000
        seed: int = req.extra.get("seed", 42)
        use_cache: bool = req.extra.get("use_cache", True)

        if not prompt_text:
            raise RuntimeError(
                "GLM-TTS（本地）需要参考音频转写文本（prompt_text），请在预设音色的「参考转写」中填写。"
            )
        if not prompt_audio_path:
            raise RuntimeError(
                "GLM-TTS（本地）需要参考音频路径，请在预设音色中配置有效的「参考音频」本地路径。"
            )

        # 优先 JSON 接口（同机）
        if prompt_audio_path:
            try:
                return await self._synthesize_json(
                    text, prompt_text, prompt_audio_path,
                    sample_rate=sample_rate, seed=seed, use_cache=use_cache,
                )
            except Exception as exc:
                logger.warning("[TTS][glm_local] json endpoint failed, falling back to multipart: %s", exc)

        # 回退 multipart
        return await self._synthesize_multipart(
            text, prompt_text, prompt_audio_path,
            sample_rate=sample_rate, seed=seed, use_cache=use_cache,
        )

    async def _synthesize_json(
        self,
        text: str,
        prompt_text: str,
        prompt_audio_path: str,
        *,
        sample_rate: int,
        seed: int,
        use_cache: bool,
    ) -> SynthesisResult:
        body: dict[str, Any] = {
            "input_text": text,
            "prompt_text": prompt_text,
            "prompt_audio_path": prompt_audio_path,
            "sample_rate": sample_rate,
            "seed": seed,
            "use_cache": use_cache,
        }
        resp = await self._client.post("/api/v1/tts/json", json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"GLM-TTS json 合成失败 ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        audio_b64: str = data.get("audio_wav_base64", "")
        if not audio_b64:
            raise RuntimeError("GLM-TTS json 响应缺少 audio_wav_base64")
        audio_bytes = base64.b64decode(audio_b64)
        return SynthesisResult(
            audio_bytes=audio_bytes,
            format="wav",
            sample_rate=data.get("sample_rate", sample_rate),
        )

    async def _synthesize_multipart(
        self,
        text: str,
        prompt_text: str,
        prompt_audio_path: str,
        *,
        sample_rate: int,
        seed: int,
        use_cache: bool,
    ) -> SynthesisResult:
        import pathlib

        # 本地 FastAPI 使用 Form + File，必须 multipart/form-data。
        # 若仅传 data 且 files=None，httpx 会发 application/x-www-form-urlencoded，
        # 服务端收不到字段，表现为 422（prompt_text / prompt_audio 为 null）。
        audio_path = pathlib.Path(prompt_audio_path)
        if not audio_path.is_file():
            raise RuntimeError(
                f"GLM-TTS（本地）参考音频不存在或无法读取: {audio_path}"
            )
        mime = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
        multipart: dict[str, Any] = {
            "input_text": (None, text),
            "prompt_text": (None, prompt_text),
            "sample_rate": (None, str(sample_rate)),
            "seed": (None, str(seed)),
            "use_cache": (None, "true" if use_cache else "false"),
            "prompt_audio": (audio_path.name, audio_path.read_bytes(), mime),
        }

        resp = await self._client.post("/api/v1/tts", files=multipart)
        if resp.status_code != 200:
            raise RuntimeError(f"GLM-TTS multipart 合成失败 ({resp.status_code}): {resp.text[:500]}")
        return SynthesisResult(
            audio_bytes=resp.content,
            format="wav",
            sample_rate=sample_rate,
        )

    # -- synthesize_stream (不支持) ----------------------------------------

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        result = await self.synthesize(req)
        yield result.audio_bytes

    # -- list_voices -------------------------------------------------------

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        """将预设中的 voiceCatalog 转为 VoiceInfo，不发起 HTTP。"""
        return [
            VoiceInfo(
                voice_id=v.get("voiceId", ""),
                name=v.get("name", v.get("voiceId", "")),
                voice_type=v.get("voiceType", "system"),
            )
            for v in self._voice_catalog
            if v.get("voiceId")
        ]

    # -- 不支持的操作 -------------------------------------------------------

    async def upload_file(
        self, file_bytes: bytes, filename: str, content_type: str | None = None,
        *, purpose: str = "voice_clone",
    ) -> UploadFileResult:
        del file_bytes, filename, content_type, purpose
        raise NotImplementedError("GLM-TTS（本地）不支持文件上传")

    async def clone_voice(
        self, *, source_file_id: str, voice_id: str, model: str | None = None,
        text: str | None = None, language_boost: str | None = None,
        prompt_audio_file_id: str | None = None, prompt_text: str | None = None,
        need_noise_reduction: bool = False, need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        raise NotImplementedError("GLM-TTS（本地）不支持云端音色复刻")

    async def design_voice(
        self, *, prompt: str, preview_text: str,
        voice_id: str | None = None, aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        raise NotImplementedError("GLM-TTS（本地）不支持音色设计")

    # -- 健康检查 -----------------------------------------------------------

    async def health_check(self) -> bool:
        """调用 GET /health 判断本地服务是否就绪。"""
        try:
            resp = await self._client.get("/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # -- 清显存 -------------------------------------------------------------

    async def clear_vram(self) -> bool:
        """调用 POST /api/v1/clear_vram 释放显存。"""
        try:
            resp = await self._client.post("/api/v1/clear_vram", timeout=30)
            return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# OmniVoice 本地实现
# ---------------------------------------------------------------------------


class OmniVoiceLocalTtsPlatform(TtsPlatform):
    """OmniVoice 本地 FastAPI 网关适配器。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8089",
        voice_catalog: list[dict[str, Any]] | None = None,
    ) -> None:
        self._base_url = _normalize_local_http_base(base_url, "http://127.0.0.1:8089")
        self._voice_catalog = voice_catalog or []
        self._http_client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=15, read=600, write=60, pool=15),
        )

    async def close(self) -> None:
        await self._http_client.aclose()

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        text = req.text.strip()
        if not text:
            raise ValueError("text 不能为空")

        instruction = str(req.extra.get("instruction") or "").strip()
        prompt_text = str(req.extra.get("prompt_text") or "").strip()
        prompt_audio_path = str(req.extra.get("prompt_audio_path") or "").strip()
        language = str(req.extra.get("language") or "").strip()

        payload: dict[str, Any] = {
            "text": text,
            "speed": req.speed or 1.0,
        }
        if language:
            payload["language"] = language

        clone_audio_bytes: bytes | None = None
        if prompt_audio_path:
            import pathlib

            audio_path = pathlib.Path(prompt_audio_path)
            if audio_path.is_file():
                clone_audio_bytes = audio_path.read_bytes()
            else:
                logger.warning("[TTS][omnivoice_local] prompt audio path is not readable: %s", audio_path)

        if clone_audio_bytes:
            payload["ref_audio_base64"] = base64.b64encode(clone_audio_bytes).decode("ascii")
            if prompt_text:
                payload["ref_text"] = prompt_text
        elif instruction:
            payload["instruct"] = instruction

        resp = await self._http_client.post("/v1/tts", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"OmniVoice 合成失败 ({resp.status_code}): {resp.text[:500]}")
        audio_bytes = resp.content
        sample_rate = _guess_wav_sample_rate(audio_bytes, req.sample_rate or 24000)
        return SynthesisResult(audio_bytes=audio_bytes, format="wav", sample_rate=sample_rate)

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        result = await self.synthesize(req)
        yield result.audio_bytes

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        del voice_type
        return [
            VoiceInfo(
                voice_id=v.get("voiceId", ""),
                name=v.get("name", v.get("voiceId", "")),
                voice_type=v.get("voiceType", "system"),
            )
            for v in self._voice_catalog
            if v.get("voiceId")
        ]

    async def upload_file(
        self, file_bytes: bytes, filename: str, content_type: str | None = None,
        *, purpose: str = "voice_clone",
    ) -> UploadFileResult:
        del file_bytes, filename, content_type, purpose
        raise NotImplementedError("OmniVoice（本地）不支持文件上传")

    async def clone_voice(
        self, *, source_file_id: str, voice_id: str, model: str | None = None,
        text: str | None = None, language_boost: str | None = None,
        prompt_audio_file_id: str | None = None, prompt_text: str | None = None,
        need_noise_reduction: bool = False, need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        del source_file_id, voice_id, model, text, language_boost
        del prompt_audio_file_id, prompt_text, need_noise_reduction, need_volume_normalization, aigc_watermark
        raise NotImplementedError("OmniVoice（本地）不支持云端音色复刻")

    async def design_voice(
        self, *, prompt: str, preview_text: str,
        voice_id: str | None = None, aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        del prompt, preview_text, voice_id, aigc_watermark
        raise NotImplementedError("OmniVoice（本地）不支持音色设计接口")

    async def health_check(self) -> bool:
        try:
            resp = await self._http_client.get("/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Qwen3-TTS 本地实现
# ---------------------------------------------------------------------------


class Qwen3LocalTtsPlatform(TtsPlatform):
    """Qwen3-TTS 本地 FastAPI 网关适配器。

    有参考音频路径且文件存在时走 ``POST /v1/tts/voice_clone``（第二端口上的 Base 模型网关）；
    否则走 ``POST /v1/tts/custom_voice``（主端口上的 CustomVoice 模型网关）。
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        voice_catalog: list[dict[str, Any]] | None = None,
        *,
        voice_clone_base_url: str | None = None,
    ) -> None:
        self._base_url = _normalize_local_http_base(base_url, "http://127.0.0.1:8080")
        self._voice_catalog = voice_catalog or []
        self._http_client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=15, read=600, write=60, pool=15),
        )
        vc_raw = (voice_clone_base_url or "").strip()
        self._voice_clone_base_url: str | None = (
            _normalize_local_http_base(vc_raw, self._base_url) if vc_raw else None
        )
        self._voice_clone_client: httpx.AsyncClient | None = None
        if self._voice_clone_base_url:
            self._voice_clone_client = httpx.AsyncClient(
                base_url=self._voice_clone_base_url,
                timeout=httpx.Timeout(connect=15, read=600, write=60, pool=15),
            )

    async def close(self) -> None:
        await self._http_client.aclose()
        if self._voice_clone_client is not None:
            await self._voice_clone_client.aclose()

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        text = req.text.strip()
        speaker = req.voice_id.strip()
        if not text:
            raise ValueError("text 不能为空")
        if not speaker:
            raise ValueError("speaker 不能为空")

        language = str(req.extra.get("language") or "Auto").strip() or "Auto"
        instruction = str(req.extra.get("instruction") or "").strip()
        prompt_text = str(req.extra.get("prompt_text") or "").strip()
        prompt_audio_path = str(req.extra.get("prompt_audio_path") or "").strip()

        if prompt_audio_path:
            audio_path = pathlib.Path(prompt_audio_path)
            if not audio_path.is_file():
                raise RuntimeError(
                    f"Qwen3-TTS（本地）参考音频不存在或无法读取: {audio_path}"
                )
            if not prompt_text:
                raise RuntimeError(
                    "Qwen3-TTS（本地）语音克隆需要参考音频转写文本（ref_text），"
                    "请在预设音色的「参考转写」中填写。"
                )
            if self._voice_clone_client is None:
                raise RuntimeError(
                    "Qwen3-TTS（本地）语音克隆需要第二套 Base 模型网关地址。"
                    "请在 TTS 预设中配置语音克隆端口（默认为主端口+1）并确保托管或手动启动该端口上的 Base 网关。"
                )
            mime = mimetypes.guess_type(str(audio_path))[0] or "audio/wav"
            multipart: dict[str, Any] = {
                "text": (None, text),
                "language": (None, language),
                "ref_text": (None, prompt_text),
                "x_vector_only": (None, "false"),
                "ref_audio": (audio_path.name, audio_path.read_bytes(), mime),
            }
            resp = await self._voice_clone_client.post("/v1/tts/voice_clone", files=multipart)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Qwen3-TTS voice_clone 合成失败 ({resp.status_code}): {resp.text[:500]}"
                )
            audio_bytes = resp.content
            sample_rate = _guess_wav_sample_rate(audio_bytes, req.sample_rate or 24000)
            return SynthesisResult(audio_bytes=audio_bytes, format="wav", sample_rate=sample_rate)

        payload = {
            "text": text,
            "speaker": speaker,
            "language": language,
            "instruct": instruction,
        }
        resp = await self._http_client.post("/v1/tts/custom_voice", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Qwen3-TTS 合成失败 ({resp.status_code}): {resp.text[:500]}")
        audio_bytes = resp.content
        sample_rate = _guess_wav_sample_rate(audio_bytes, req.sample_rate or 24000)
        return SynthesisResult(audio_bytes=audio_bytes, format="wav", sample_rate=sample_rate)

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        result = await self.synthesize(req)
        yield result.audio_bytes

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        del voice_type
        return [
            VoiceInfo(
                voice_id=v.get("voiceId", ""),
                name=v.get("name", v.get("voiceId", "")),
                voice_type=v.get("voiceType", "system"),
            )
            for v in self._voice_catalog
            if v.get("voiceId")
        ]

    async def upload_file(
        self, file_bytes: bytes, filename: str, content_type: str | None = None,
        *, purpose: str = "voice_clone",
    ) -> UploadFileResult:
        del file_bytes, filename, content_type, purpose
        raise NotImplementedError("Qwen3-TTS（本地）不支持文件上传")

    async def clone_voice(
        self, *, source_file_id: str, voice_id: str, model: str | None = None,
        text: str | None = None, language_boost: str | None = None,
        prompt_audio_file_id: str | None = None, prompt_text: str | None = None,
        need_noise_reduction: bool = False, need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        del source_file_id, voice_id, model, text, language_boost
        del prompt_audio_file_id, prompt_text, need_noise_reduction, need_volume_normalization, aigc_watermark
        raise NotImplementedError("Qwen3-TTS（本地）不支持云端音色复刻")

    async def design_voice(
        self, *, prompt: str, preview_text: str,
        voice_id: str | None = None, aigc_watermark: bool = False,
    ) -> VoiceDesignResult:
        del prompt, preview_text, voice_id, aigc_watermark
        raise NotImplementedError("Qwen3-TTS（本地）不支持音色设计")

    async def health_check(self) -> bool:
        try:
            r1 = await self._http_client.get("/health", timeout=5)
            if r1.status_code != 200:
                return False
            if self._voice_clone_client is not None:
                r2 = await self._voice_clone_client.get("/health", timeout=5)
                return r2.status_code == 200
            return True
        except Exception:
            return False
