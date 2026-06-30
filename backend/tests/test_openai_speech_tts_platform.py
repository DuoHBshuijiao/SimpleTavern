"""OpenRouter / 硅基流动 OpenAI-style speech 适配器单元测试。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services.tts_platform import (
    OpenAiSpeechCompatTtsPlatform,
    SynthesisRequest,
    _normalize_openrouter_speech_base,
    _normalize_siliconflow_speech_base,
)


@pytest.mark.parametrize(
    ("raw", "expected_suffix"),
    [
        ("https://openrouter.ai", "/api/v1"),
        ("openrouter.ai/api/v1/audio/speech", "/api/v1"),
        ("https://openrouter.ai/api/v1", "/api/v1"),
    ],
)
def test_normalize_openrouter_speech_base(raw: str, expected_suffix: str) -> None:
    out = _normalize_openrouter_speech_base(raw)
    assert out.endswith(expected_suffix.rstrip("/"))
    assert "audio/speech" not in out.lower()


def test_normalize_siliconflow_defaults() -> None:
    assert _normalize_siliconflow_speech_base("").endswith("/v1")


def test_siliconflow_synthesize_non_stream_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, content=b"\xff\xfb\x90", headers={"content-type": "audio/mpeg"})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        raw_client = httpx.AsyncClient(transport=transport, base_url="https://api.siliconflow.cn/v1")
        plat = OpenAiSpeechCompatTtsPlatform(
            api_key="sk-test",
            base_url="https://api.siliconflow.cn/v1",
            variant="siliconflow",
        )
        plat._client = raw_client  # type: ignore[method-assign]
        try:
            req = SynthesisRequest(
                text="hi",
                voice_id="FunAudioLLM/CosyVoice2-0.5B:alex",
                model="FunAudioLLM/CosyVoice2-0.5B",
                audio_format="mp3",
            )
            result = await plat.synthesize(req)
            payload = json.loads(captured["body"])
            assert payload["stream"] is False
            assert "/audio/speech" in captured["url"]
            assert result.format == "mp3"
            assert len(result.audio_bytes) > 0
        finally:
            await plat.close()

    asyncio.run(_run())


def test_siliconflow_upload_reference_voice_multipart() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(200, json={"uri": "speech:test:abc:def"})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        raw_client = httpx.AsyncClient(transport=transport, base_url="https://api.siliconflow.cn/v1")
        plat = OpenAiSpeechCompatTtsPlatform(
            api_key="sk-test",
            base_url="https://api.siliconflow.cn/v1",
            variant="siliconflow",
        )
        plat._client = raw_client  # type: ignore[method-assign]
        try:
            out = await plat.upload_reference_voice(
                file_bytes=b"id3",
                filename="x.mp3",
                content_type="audio/mpeg",
                model="FunAudioLLM/CosyVoice2-0.5B",
                custom_name="my-voice",
                text="示例转写",
            )
            assert out.voice_id == "speech:test:abc:def"
            assert "multipart/form-data" in captured["content_type"]
        finally:
            await plat.close()

    asyncio.run(_run())


def test_openrouter_synthesize_no_stream_field() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, content=b"\xff\xfb", headers={"content-type": "audio/mpeg"})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        raw_client = httpx.AsyncClient(transport=transport, base_url="https://openrouter.ai/api/v1")
        plat = OpenAiSpeechCompatTtsPlatform(
            api_key="sk-or",
            base_url="https://openrouter.ai/api/v1",
            variant="openrouter",
        )
        plat._client = raw_client  # type: ignore[method-assign]
        try:
            req = SynthesisRequest(
                text="Hello",
                voice_id="alloy",
                model="google/gemini-3.1-flash-tts-preview",
                audio_format="mp3",
            )
            await plat.synthesize(req)
            assert "stream" not in captured["body"].lower()
            assert "provider" not in captured["body"].lower()
        finally:
            await plat.close()

    asyncio.run(_run())
