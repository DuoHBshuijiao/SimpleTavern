"""T-802 batch 6: TTS / infra observability contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import glm_local_tts_process
from app.services import http_log as http_log_service
from app.services.tts_platform import GlmLocalTtsPlatform, OpenAiSpeechCompatTtsPlatform, SynthesisResult
from app.tokenizer_service import count_tokens, get_tokenizer_health, trim_dict_messages_to_token_budget


@pytest.mark.asyncio
async def test_glm_local_json_fallback_emits_warning() -> None:
    platform = GlmLocalTtsPlatform(base_url="http://127.0.0.1:8088")
    platform._synthesize_json = AsyncMock(side_effect=RuntimeError("json down"))  # type: ignore[method-assign]
    platform._synthesize_multipart = AsyncMock(  # type: ignore[method-assign]
        return_value=SynthesisResult(audio_bytes=b"WAV", format="wav", sample_rate=24000),
    )
    from app.services.tts_platform import SynthesisRequest

    result = await platform.synthesize(
        SynthesisRequest(
            text="hello",
            voice_id="v1",
            extra={"prompt_text": "ref", "prompt_audio_path": "C:/a.wav"},
        )
    )
    assert result.audio_bytes == b"WAV"
    assert result.warnings
    assert result.warnings[0]["code"] == "tts_endpoint_fallback"
    assert result.warnings[0]["from"] == "/api/v1/tts/json"
    assert result.warnings[0]["to"] == "/api/v1/tts"
    await platform.close()


@pytest.mark.asyncio
async def test_siliconflow_voice_list_partial_on_http_error() -> None:
    platform = OpenAiSpeechCompatTtsPlatform(
        base_url="https://api.siliconflow.cn/v1",
        api_key="sk-test",
        variant="siliconflow",
    )
    response = httpx.Response(500, request=httpx.Request("GET", "https://api.siliconflow.cn/v1/audio/voice/list"))
    with patch.object(platform._client, "get", new=AsyncMock(return_value=response)):
        detailed = await platform.list_voices_detailed()
    assert detailed.partial_success is True
    assert detailed.voices  # presets remain
    assert detailed.warnings[0]["code"] == "tts_voice_list_partial"
    await platform.close()


def test_glm_local_process_health_records_start_failure(tmp_path) -> None:
    import asyncio

    async def _run() -> None:
        ok = await glm_local_tts_process.start(str(tmp_path / "missing-repo"), port=18088)
        assert ok is False
        health = glm_local_tts_process.get_health()
        assert health["failureCount"] >= 1
        assert health["code"] == "tts_local_process_start_failed"
        assert health["lastError"] is not None

    asyncio.run(_run())


def test_health_poll_timeout_does_not_double_count_failures() -> None:
    import asyncio

    async def _run() -> None:
        glm_local_tts_process._failure_count = 0
        glm_local_tts_process._last_error = None
        glm_local_tts_process._last_code = None
        ok = await glm_local_tts_process._health_poll(
            "http://127.0.0.1:1",
            retries=1,
            interval=0,
        )
        assert ok is False
        # poll 本身不记账；由调用方 start() 统一记录一次
        assert glm_local_tts_process.get_health()["failureCount"] == 0

    asyncio.run(_run())


def test_glm_local_health_reachable_clears_stale_top_level_error(monkeypatch) -> None:
    import asyncio
    from app.routes import tts as tts_routes
    from app.schemas import Settings, ApiPreset
    from app.services.tts_platform import GlmLocalTtsPlatform

    glm_local_tts_process._failure_count = 3
    glm_local_tts_process._last_code = "tts_local_process_start_failed"
    glm_local_tts_process._last_error = {
        "code": "tts_local_process_start_failed",
        "message": "stale",
    }

    preset = ApiPreset(
        id="p1",
        name="glm",
        presetKind="tts",
        ttsProvider="glm_local",
        ttsGlmLocalPort=8088,
    )
    settings = Settings(ttsEnabled=True, apiPresets=[preset], activeApiPresetId="p1")
    monkeypatch.setattr(tts_routes, "_require_tts_enabled", lambda: settings)
    monkeypatch.setattr(tts_routes, "_resolve_tts_preset", lambda _s, _pid=None: preset)

    platform = GlmLocalTtsPlatform(base_url="http://127.0.0.1:8088")
    platform.health_check_detail = AsyncMock(  # type: ignore[method-assign]
        return_value={"ok": True, "code": None, "lastError": None},
    )
    platform.close = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(tts_routes, "_get_platform", lambda *_a, **_k: platform)

    body = asyncio.run(tts_routes.glm_local_health(tts_routes.GlmLocalActionReq()))
    assert body["ok"] is True
    assert body["health"]["reachable"] is True
    assert body["health"]["code"] is None
    assert body["health"]["lastError"] is None
    assert body["health"]["process"]["failureCount"] == 0


def test_http_log_write_failure_increments_counter(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(http_log_service, "get_http_log_dir", lambda: tmp_path)
    before = http_log_service.get_health()["writeFailedCount"]

    class BoomPath:
        def mkdir(self, *a, **k):
            raise OSError("disk full")

        def __truediv__(self, _other):
            return self

    monkeypatch.setattr(http_log_service, "_shard_path", lambda _ts: BoomPath())
    http_log_service._write_record_sync({"id": "r1", "ts": 1, "source": "test", "method": "GET", "url": "x"})
    after = http_log_service.get_health()
    assert after["writeFailedCount"] == before + 1
    assert after["lastWriteError"]["code"] == "http_log_write_failed"


def test_tokenizer_unavailable_is_not_zero(monkeypatch) -> None:
    monkeypatch.setattr("app.tokenizer_service._tokenizer_instance", None)
    monkeypatch.setattr("app.tokenizer_service._get_tokenizer", lambda: None)
    assert count_tokens("") == 0
    assert count_tokens("hello") is None
    health = get_tokenizer_health()
    assert health["available"] is False
    assert health["code"] == "tokenizer_unavailable"
    kept, warnings = trim_dict_messages_to_token_budget(
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        1,
    )
    assert len(kept) == 2
    assert "tokenizer_unavailable" in warnings


def test_resolve_system_tokens_skips_fake_zero() -> None:
    from app.routes import generate as gen

    warnings: list[dict] = []
    with patch("app.routes.generate.count_tokens", return_value=None):
        tokens, ok = gen._resolve_system_tokens_for_budget("sys", warnings_out=warnings)
    assert ok is False
    assert tokens == 0
    assert warnings[0]["code"] == "tokenizer_unavailable"
