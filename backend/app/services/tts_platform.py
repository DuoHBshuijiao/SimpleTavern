"""
TTS 平台抽象层

定义 TtsPlatform 接口与 MiniMax 实现。
其他厂商（OpenAI TTS、Azure 等）可继承 TtsPlatform 实现。
"""

from __future__ import annotations

import abc
import logging
import mimetypes
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

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

# ---------------------------------------------------------------------------
# 通用数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VoiceInfo:
    voice_id: str
    name: str
    voice_type: str  # system | voice_cloning | voice_generation


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
    file_id: int


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
        source_file_id: int,
        voice_id: str,
        model: str | None = None,
        text: str | None = None,
        language_boost: str | None = None,
        prompt_audio_file_id: int | None = None,
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
        return UploadFileResult(file_id=int(file_id))

    async def clone_voice(
        self,
        *,
        source_file_id: int,
        voice_id: str,
        model: str | None = None,
        text: str | None = None,
        language_boost: str | None = None,
        prompt_audio_file_id: int | None = None,
        prompt_text: str | None = None,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
        aigc_watermark: bool = False,
    ) -> VoiceCloneResult:
        body: dict[str, Any] = {
            "file_id": source_file_id,
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
                "prompt_audio": prompt_audio_file_id,
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
