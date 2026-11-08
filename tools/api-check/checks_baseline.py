"""对照：同一套流程走本分支已有的协议。

这一组通过、而 t832 失败，才能说明 t832 的失败来自协议不支持，不是检查流程本身有问题。
"""
import json

from harness import add_check, contains_text, ensure, equal
from mock_upstream import REPLY, THINKING, TOOL_FINAL_REPLY, USAGE

USER_TEXT = "请描述一下长廊。"
MODEL = "mock-model"


def _preset(env, protocol):
    key = env.fixtures["openai_key"]
    preset = {"id": f"baseline-{protocol}", "name": f"对照 {protocol}", "baseUrl": env.mock.url + ("/v1" if protocol == "openai_compatible_chat" else ""),
              "apiKey": key, "models": [MODEL], "protocol": protocol, "promptCache": {"mode": "off"}}
    env.put_preset(preset)
    env.mock.api_key = key
    env.mock.expect_model = None
    return preset["id"]


def _chat(env, protocol, stream=True, reasoning="high", **mock_options):
    preset_id = _preset(env, protocol)
    env.set_stream(stream)
    env.mock.reset(**mock_options)
    env.mock.api_key = env.fixtures["openai_key"]
    return env.new_chat(preset_id, MODEL, reasoning=reasoning, max_tokens=4096)


def stream_ok(protocol, route):
    def run(env):
        chat_id = _chat(env, protocol)
        result = env.generate(chat_id, USER_TEXT)
        ensure(env.mock.calls(route), f"请求应到模拟上游：{result.summary()}；{env.mock.requests}")
        ensure(result.succeeded, result.summary())
        equal(result.text, REPLY, "delta 拼接")
        equal(result.reasoning, THINKING, "reasoning 拼接")
        chat = env.read_chat(chat_id)
        equal(chat["messages"][-2]["content"], USER_TEXT, "用户消息落盘")
        last = chat["messages"][-1]
        equal(last["content"], REPLY, "助手消息落盘")
        equal(last["id"], result.done.get("assistantMessageId"), "assistantMessageId")
        equal(last.get("reasoningContent"), THINKING, "思考落盘")
        equal(last["usage"].get("inputTokens"), USAGE["input"], "inputTokens")
        equal(last["usage"].get("outputTokens"), USAGE["output"], "outputTokens")
        equal(last["usage"].get("totalTokens"), USAGE["total"], "totalTokens")
        equal(last["generationMetadata"].get("protocol"), protocol, "generationMetadata.protocol")
        summary = env.usage_summary(chat_id)
        equal(summary.get("completedCount"), 1, "账本 completedCount")
        equal(summary.get("inputTokens"), USAGE["input"], "账本 inputTokens")
    return run


def once_ok(protocol, route):
    def run(env):
        chat_id = _chat(env, protocol, stream=False)
        result = env.generate(chat_id, USER_TEXT)
        ensure(env.mock.calls(route), f"请求应到模拟上游：{result.summary()}；{env.mock.requests}")
        ensure(result.succeeded, result.summary())
        ensure(not result.is_sse, "streamEnabled=false 时应是 JSON")
        chat = env.read_chat(chat_id)
        equal(chat["messages"][-1]["content"], REPLY, "助手消息落盘")
        equal(chat["messages"][-1]["usage"].get("inputTokens"), USAGE["input"], "inputTokens")
        ensure(contains_text(result.json, REPLY), f"响应体应有助手正文：{json.dumps(result.json, ensure_ascii=False)[:400]}")
    return run


def http_error(protocol, route, status):
    def run(env):
        chat_id = _chat(env, protocol, fault=f"http_{status}")
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        ensure(env.mock.calls(route), f"请求应到模拟上游：{result.summary()}；{env.mock.requests}")
        ensure(not result.succeeded and result.error, result.summary())
        error = result.error
        for key in ("code", "message", "requestId"):
            ensure(error.get(key), f"错误缺少 {key}：{error}")
        if status in (401, 403):
            equal(error["code"], "provider_auth_failed", "code")
            equal(error.get("retryable"), False, "retryable")
        else:
            equal(error.get("retryable"), True, "retryable")
        messages = env.read_chat(chat_id)["messages"]
        ensure(any(m["role"] == "user" and m["content"] == USER_TEXT for m in messages), "用户消息不能丢")
        equal(env.usage_summary(chat_id).get("completedCount"), 0, "completedCount")
    return run


def truncated(protocol, route):
    def run(env):
        chat_id = _chat(env, protocol, fault="truncate")
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        ensure(env.mock.calls(route), f"请求应到模拟上游：{result.summary()}")
        ensure(not result.hung and not result.transport_error, result.summary())
        ensure(not result.succeeded and result.error, f"断流不能算成功：{result.summary()}")
        equal(result.error.get("terminal"), True, "terminal")
        equal(env.usage_summary(chat_id).get("completedCount"), 0, "completedCount")
    return run


def tool_round(env):
    protocol = "anthropic_messages"
    preset_id = _preset(env, protocol)
    env.set_stream(True)
    env.api.json_ok("PUT", "/api/assistant/settings", json={"presetId": preset_id, "model": MODEL, "reasoningEffort": "none"})
    env.api.json_ok("POST", "/api/assistant/reset", params={"scope": "workspace"})
    env.mock.reset(tool_round=True)
    env.mock.api_key = env.fixtures["openai_key"]
    result = env.api.stream("/api/assistant/stream", {"userMessage": "看一下现有内容。", "scope": "workspace", "model": MODEL}, deadline=60.0)
    calls = env.mock.calls("anthropic")
    ensure(env.mock.tool_used, f"请求应带工具定义：{result.summary()}；{env.mock.requests}")
    ensure(len(calls) >= 2, f"工具结果应再发一轮，实际 {len(calls)} 轮：{result.summary()}")
    ensure(result.succeeded, result.summary())
    ensure(TOOL_FINAL_REPLY in result.text, f"最后的回答应流给前端：{result.text[:200]!r}")
    chat = env.api.json_ok("GET", "/api/assistant/chat", params={"scope": "workspace"})
    ensure(any(TOOL_FINAL_REPLY in (m.get("content") or "") for m in chat["messages"]), "最后的回答应落盘")


def secret_scan_is_not_vacuous(env):
    """HTTP 日志确实记录出站请求，否则 t832 的密钥扫描扫不到东西。"""
    chat_id = _chat(env, "openai_compatible_chat")
    env.api.json_ok("DELETE", "/api/http-log")
    result = env.generate(chat_id, USER_TEXT)
    ensure(result.succeeded, result.summary())
    items = env.api.json_ok("GET", "/api/http-log").get("items", [])
    ensure(items, "HTTP 日志应记录这次出站请求")
    record_id = items[0].get("id") or items[0].get("recordId")
    ensure(record_id, f"日志记录应有 id：{items[0]}")
    detail = env.api.get(f"/api/http-log/{record_id}").text
    ensure("/v1/chat/completions" in detail or "/v1/chat/completions" in json.dumps(items[0]), f"日志详情应有请求地址：{detail[:300]}")
    ensure(env.fixtures["openai_key"] not in detail, "现有协议的日志也不该有明文 Key")


for _protocol, _route in (("openai_compatible_chat", "openai"), ("anthropic_messages", "anthropic")):
    add_check(f"baseline.{_protocol}.stream", "现有协议流式：文字、思考、用量、落盘、账本", stream_ok(_protocol, _route))
    add_check(f"baseline.{_protocol}.once", "现有协议非流式：文字、用量、落盘", once_ok(_protocol, _route))
    for _status in (401, 403, 429, 500):
        add_check(f"baseline.{_protocol}.http_{_status}", f"现有协议上游 {_status} 的错误映射", http_error(_protocol, _route, _status))
    add_check(f"baseline.{_protocol}.truncate", "现有协议断流不算成功", truncated(_protocol, _route))
add_check("baseline.anthropic_messages.tool_round", "现有协议的助手工具往返", tool_round)
add_check("baseline.http_log_records", "HTTP 日志确实记录出站请求，且没有明文 Key", secret_scan_is_not_vacuous)
