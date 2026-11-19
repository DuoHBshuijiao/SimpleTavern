"""DeepSeek 整段合成的公开 HTTP 契约和 SimpleTavern 资产行为。"""

import io
import json
import socket
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlsplit

from harness import assert_rest_error, check, ensure, equal


@contextmanager
def configured(env, fault="ok", two_presets=False):
    saved = env.settings()
    key = env.fixtures["openai_key"]
    preset = {"id": "check-deepseek", "name": "DeepSeek 检查", "presetKind": "tts",
              "ttsProvider": "deepseek", "baseUrl": env.mock.url + "/v1", "apiKey": key}
    env.mock.reset(fault=fault)
    env.mock.api_key = key
    try:
        env.update_settings(ttsEnabled=True, apiPresets=[preset, {**preset, "id": "check-deepseek-two"}] if two_presets else [preset])
        yield {"preset_id": preset["id"], "voice_id": "stella"}
    finally:
        env.api.json_ok("PUT", "/api/settings", json=saved)
        env.mock.reset()


def synth(env, body, **change):
    return env.api.json_ok("POST", "/api/tts/synthesize", json={**body, **change})


def message(env):
    chat = env.new_chat()
    payload = env.api.json_ok("POST", f"/api/chats/{chat}/messages", json={"role": "assistant", "content": "用来朗读。"})
    return {"chat_id": chat, "message_id": payload["messages"][-1]["id"]}


def bound_asset(env, target):
    return next(m for m in env.read_chat(target["chat_id"])["messages"] if m["id"] == target["message_id"]).get("ttsAudioAssetId")


def read_wave(env, result):
    equal(result["format"], "wav", "缓存格式")
    audio = env.api.get("/api/tts/audio/" + result["assetId"])
    equal(audio.status_code, 200, "缓存可读取")
    equal(len(audio.content), result["sizeBytes"], "缓存字节数")
    ensure(audio.headers["Content-Type"].startswith("audio/wav"), "缓存媒体类型")
    with wave.open(io.BytesIO(audio.content)) as wav:
        equal(wav.getframerate(), 24000, "缓存采样率")
        equal(len(wav.readframes(241)), 480, "完整的 240 音频帧")
    return audio.content


@check("deepseek_tts.catalog", "常用音色列表不要求密钥，也不发出上游请求")
def _(env):
    saved = env.settings()
    try:
        env.update_settings(ttsEnabled=True)
        calls = len(env.mock.calls("deepseek_tts"))
        data = env.api.json_ok("POST", "/api/tts/test-voices",
                               json={"baseUrl": env.mock.url, "apiKey": "", "provider": "deepseek"})
        equal({(item["voiceId"], item["name"]) for item in data["voices"]},
              {("stella", "海星"), ("tide", "暗潮")}, "内置音色")
        equal(len(env.mock.calls("deepseek_tts")), calls, "音色目录没有消耗合成请求")
    finally:
        env.api.json_ok("PUT", "/api/settings", json=saved)


@check("deepseek_tts.chunked_cache", "接收分块 WAV，缓存按预设、音色和实际稿件隔离")
def _(env):
    with configured(env, two_presets=True) as body:
        target = message(env)
        text = "你好，**这是第一份稿件**。"
        first = synth(env, body, text=text, **target)
        stella = read_wave(env, first)
        equal(bound_asset(env, target), first["assetId"], "合成完成后绑定")
        equal(synth(env, body, text=text)["assetId"], first["assetId"], "同一份稿件命中")
        equal(len(env.mock.calls("deepseek_tts")), 1, "缓存命中不重新访问上游")
        other = synth(env, body, text=text, voice_id="tide")
        ensure(read_wave(env, other) != stella, "换音色后实际音频不同")
        edited = synth(env, body, text="改过的朗读稿。")
        separate = synth(env, body, text=text, preset_id="check-deepseek-two")
        equal(len({part["assetId"] for part in (first, other, edited, separate)}), 4, "四个缓存互相隔离")
        record = env.mock.calls("deepseek_tts")[0]
        equal(record.json, {"text": text, "voice_id": "stella", "format": "wav", "filter_markdown": True}, "上游请求字段")
        equal(record.headers.get("Authorization"), f"Bearer {env.fixtures['openai_key']}", "上游 Bearer 鉴权")
        ensure(len(record.raw) <= 65536, "实际发送的 JSON 字节数合法")

        preset = next(p for p in env.settings()["apiPresets"] if p["id"] == body["preset_id"])
        env.put_preset({**preset, "baseUrl": env.mock.url + "/v1/tools/tts"})
        equal(synth(env, body, text=text)["assetId"], first["assetId"], "同一服务的完整地址与基址共用缓存")
        env.put_preset({**preset, "baseUrl": env.mock.url.replace("127.0.0.1", "localhost")})
        ensure(synth(env, body, text=text)["assetId"] != first["assetId"], "缓存按服务地址隔离")

        before = len(env.mock.calls("deepseek_tts"))
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: synth(env, body, text="同时请求同一份朗读稿。"), range(2)))
        equal(results[0]["assetId"], results[1]["assetId"], "同时请求同一合成返回同一个资产")
        equal(len(env.mock.calls("deepseek_tts")), before + 1, "并发请求共用一次上游合成")

        already_bound = bound_asset(env, target)
        synth(env, body, text="迟到的音频。", content_text="消息已改写前的文字。", **target)
        equal(bound_asset(env, target), already_bound, "迟到的合成不覆盖已改写消息的绑定")


@check("deepseek_tts.limits", "汉字双计费、空白与无效音色在发送前校验")
def _(env):
    with configured(env) as body:
        synth(env, body, text="汉" * 5000)
        for updates, marker in (({"text": "汉" * 5000 + "a"}, "10,000"),
                                ({"text": "   "}, "文本"),
                                ({"text": "试听", "voice_id": "custom"}, "音色")):
            response = env.api.post("/api/tts/synthesize", json={**body, **updates})
            detail = assert_rest_error(response, 422)
            ensure(marker in detail["message"], detail)
        equal(len(env.mock.calls("deepseek_tts")), 1, "超限及无效请求没有发送到上游")


@check("deepseek_tts.unknown_wave_size", "未知 RIFF 长度的完整 WAV 收完后可正常播放")
def _(env):
    with configured(env, fault="tts_unknown_size") as body:
        read_wave(env, synth(env, body, text="未知长度测试。"))


@check("deepseek_tts.failed_audio", "明确断流、空音频及可检测截断不会绑定消息或留下可复用音频")
def _(env):
    for fault in ("tts_truncated", "tts_disconnect", "tts_empty"):
        with configured(env, fault=fault) as body:
            target = message(env)
            text = f"故障重试 {fault}"
            assert_rest_error(env.api.post("/api/tts/synthesize", json={**body, **target, "text": text}), 502)
            equal(bound_asset(env, target), None, "失败时没有绑定消息")
            env.mock.fault = "ok"
            read_wave(env, synth(env, body, text=text, **target))
            equal(len(env.mock.calls("deepseek_tts")), 2, "失败后同样请求重新合成")


@check("deepseek_tts.upstream_errors", "审核、并发限流、繁忙和超时反馈各自的原因")
def _(env):
    for fault, status, marker in (("tts_reject", 400, "审核"), ("tts_rate", 429, "并发"),
                                  ("tts_busy", 503, "繁忙"), ("tts_timeout", 504, "超时")):
        with configured(env, fault=fault) as body:
            response = env.api.post("/api/tts/synthesize", json={**body, "text": "错误分辨 " + fault})
            detail = assert_rest_error(response, status)
            ensure(marker in detail["message"], detail)


@check("deepseek_tts.cancel", "断开调用方后，同一句重试需要重新合成")
def _(env):
    with configured(env, fault="tts_slow") as body:
        target = message(env)
        text = "取消上下游请求测试。"
        address = urlsplit(env.api.base)
        raw = json.dumps({**body, **target, "text": text}).encode()
        with socket.create_connection((address.hostname, address.port), timeout=5) as client:
            headers = (f"POST /api/tts/synthesize HTTP/1.1\r\nHost: {address.netloc}\r\n"
                       f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n\r\n")
            client.sendall(headers.encode() + raw)
            deadline = time.monotonic() + 3
            while not env.mock.calls("deepseek_tts") and time.monotonic() < deadline:
                time.sleep(0.02)
            equal(len(env.mock.calls("deepseek_tts")), 1, "先确认上游已经开始返回")
        time.sleep(1.3)
        equal(bound_asset(env, target), None, "断开客户端时没有绑定")
        env.mock.fault = "ok"
        read_wave(env, synth(env, body, text=text, **target))
        equal(len(env.mock.calls("deepseek_tts")), 2, "取消请求没有污染缓存")
