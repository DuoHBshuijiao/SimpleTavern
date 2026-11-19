"""DeepSeek whole-text synthesis. A response is playable only after the WAV is complete."""

from __future__ import annotations

import hashlib
import json
import struct
from typing import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import httpx
import regex

from app.errors import AppError
from app.services.tts_platform import SynthesisRequest, SynthesisResult, TtsPlatform, VoiceInfo

DEEPSEEK_TTS_BASE = "https://api.deepseek.com"
DEEPSEEK_VOICES = (VoiceInfo("stella", "海星", "system"), VoiceInfo("tide", "暗潮", "system"))
_VOICE_IDS = frozenset(voice.voice_id for voice in DEEPSEEK_VOICES)
_HAN = regex.compile(r"\p{Han}")
_UNKNOWN_SIZE = frozenset({0, 0xFFFFFFFF})
_MAX_AUDIO_BYTES = 192 * 1024 * 1024


def _error(code: str, message: str, status: int) -> AppError:
    return AppError(code=code, message=message, source="tts", provider="deepseek",
                    status_code=status, retryable=status in {429, 502, 503, 504})


def _incomplete_audio() -> AppError:
    return _error("tts_audio_incomplete", "DeepSeek 返回的 WAV 音频为空或不完整，请重试。", 502)


def _endpoint(base_url: str) -> str:
    base = base_url.strip() or DEEPSEEK_TTS_BASE
    if "://" not in base:
        base = "https://" + base
    try:
        parsed = urlsplit(base)
        _ = parsed.port
    except ValueError:
        raise _error("tts_invalid_endpoint", "DeepSeek TTS 服务地址无效。", 422) from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or (
        parsed.query or parsed.fragment
    ):
        raise _error("tts_invalid_endpoint", "请输入有效的 DeepSeek TTS 服务基址。", 422)
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1/tools/tts"):
        path += "/tools/tts" if path.endswith("/v1") else "/v1/tools/tts"
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), path, "", ""))


def _request_bytes(req: SynthesisRequest) -> bytes:
    if not req.text.strip():
        raise _error("tts_empty_text", "请输入可朗读的文本。", 422)
    if req.voice_id not in _VOICE_IDS:
        raise _error("tts_invalid_voice", "DeepSeek 音色请选择海星或暗潮。", 422)
    if len(req.text) + len(_HAN.findall(req.text)) > 10_000:
        raise _error("tts_text_too_long", "DeepSeek 单次最多朗读 10,000 个计费字符，汉字按两个计。请缩短文本或更换预设。", 422)
    body = {"text": req.text, "voice_id": req.voice_id, "format": "wav", "filter_markdown": True}
    try:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except UnicodeEncodeError:
        raise _error("tts_invalid_text", "朗读文本含有无法编码的字符。", 422) from None
    if len(payload) > 64 * 1024:
        raise _error("tts_text_too_long", "DeepSeek 单次请求上限为 64 KiB。请缩短文本或更换预设。", 422)
    return payload


def complete_deepseek_wav(audio: bytearray) -> SynthesisResult:
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise _incomplete_audio()
    riff_size = struct.unpack_from("<I", audio, 4)[0]
    if riff_size not in _UNKNOWN_SIZE and riff_size + 8 != len(audio):
        raise _incomplete_audio()

    position = 12
    sample_rate = block_align = 0
    found_data = False
    while position + 8 <= len(audio):
        kind = audio[position:position + 4]
        size = struct.unpack_from("<I", audio, position + 4)[0]
        start = position + 8
        if kind == b"data":
            if found_data or not block_align:
                raise _incomplete_audio()
            if size == 0xFFFFFFFF or (size == 0 and riff_size in _UNKNOWN_SIZE):
                # A streaming data chunk with no size owns the rest of the response.
                size = len(audio) - start
                struct.pack_into("<I", audio, position + 4, size)
                if size % 2:
                    audio.append(0)
            if size == 0 or size % block_align:
                raise _incomplete_audio()
            found_data = True
        end = start + size + (size % 2)
        if end > len(audio):
            raise _incomplete_audio()
        if kind == b"fmt ":
            if size < 16 or sample_rate:
                raise _incomplete_audio()
            encoding, channels, sample_rate, _, block_align, bits = struct.unpack_from("<HHIIHH", audio, start)
            if encoding not in (1, 3, 0xFFFE) or not channels or not sample_rate or not bits or (
                block_align != channels * ((bits + 7) // 8) or (encoding == 0xFFFE and size < 40)
            ):
                raise _incomplete_audio()
        position = end
    if not found_data or position != len(audio):
        raise _incomplete_audio()
    struct.pack_into("<I", audio, 4, len(audio) - 8)
    return SynthesisResult(bytes(audio), "wav", sample_rate)


async def _raise_upstream_error(response: httpx.Response) -> None:
    status = response.status_code
    if status == 400:
        detail = bytearray()
        async for chunk in response.aiter_bytes():
            detail.extend(chunk[:8192 - len(detail)])
            if len(detail) >= 8192:
                break
        if b"content exists risk" in detail.lower():
            raise _error("tts_content_rejected", "文本未通过 DeepSeek 内容审核。", 400)
        raise _error("tts_input_rejected", "DeepSeek 未找到可朗读的文本或拒绝了请求。", 400)
    if status in (401, 403):
        raise _error("tts_auth_failed", "DeepSeek 鉴权失败，请检查 TTS 预设的 API Key。", status)
    if status == 429:
        raise _error("tts_rate_limited", "DeepSeek 达到并发请求上限，请稍后重试。", 429)
    if status == 503:
        raise _error("tts_service_busy", "DeepSeek 语音合成服务繁忙，请稍后重试。", 503)
    if status == 504:
        raise _error("tts_timeout", "DeepSeek 语音合成超时，请稍后重试。", 504)
    raise _error("tts_upstream_error", f"DeepSeek 语音合成失败（HTTP {status}）。", 502)


class DeepSeekTtsPlatform(TtsPlatform):
    def __init__(self, api_key: str, base_url: str = DEEPSEEK_TTS_BASE) -> None:
        self._api_key = api_key
        self._endpoint = _endpoint(base_url)

    def cache_asset_id(self, preset_id: str, req: SynthesisRequest) -> str:
        identity = json.dumps(["deepseek-wav-v1", preset_id, self._endpoint], separators=(",", ":")).encode()
        digest = hashlib.sha256(identity + b"\0" + _request_bytes(req)).hexdigest()
        return "ds" + digest[:62]

    async def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        payload = _request_bytes(req)
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        audio = bytearray()
        try:
            timeout = httpx.Timeout(connect=10, read=120, write=30, pool=10)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", self._endpoint, headers=headers, content=payload) as response:
                    if not response.is_success:
                        await _raise_upstream_error(response)
                    if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "audio/wav":
                        raise _incomplete_audio()
                    async for chunk in response.aiter_bytes():
                        if len(audio) + len(chunk) > _MAX_AUDIO_BYTES:
                            raise _error("tts_audio_too_large", "DeepSeek 返回的 WAV 音频超出缓存容量。", 502)
                        audio.extend(chunk)
        except httpx.TimeoutException:
            raise _error("tts_timeout", "DeepSeek 语音合成超时，请稍后重试。", 504) from None
        except httpx.RemoteProtocolError:
            raise _error("tts_connection_lost", "DeepSeek 音频传输中断，请重试。", 502) from None
        except httpx.HTTPError:
            raise _error("tts_connection_failed", "DeepSeek 语音合成连接失败，请检查服务地址或网络。", 502) from None
        return complete_deepseek_wav(audio)

    async def synthesize_stream(self, req: SynthesisRequest) -> AsyncIterator[bytes]:
        yield (await self.synthesize(req)).audio_bytes

    async def list_voices(self, voice_type: str = "all") -> list[VoiceInfo]:
        return list(DEEPSEEK_VOICES) if voice_type in {"all", "system"} else []

    async def upload_file(self, *args, **kwargs):
        raise _error("tts_unsupported", "DeepSeek 朗读使用内置音色。", 422)

    async def clone_voice(self, **kwargs):
        raise _error("tts_unsupported", "DeepSeek 朗读使用内置音色。", 422)

    async def design_voice(self, **kwargs):
        raise _error("tts_unsupported", "DeepSeek 朗读使用内置音色。", 422)
