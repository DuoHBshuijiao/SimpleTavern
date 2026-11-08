"""T-832 三家协议的黑盒检查。

每一项都先确认请求真的到了模拟上游。协议不支持时，后端也可能回一个结构化错误，
如果不先确认这一点，负向检查会误判为通过。
"""
import json
import time
from dataclasses import dataclass, field

import fixtures
from harness import CheckFailed, add_check, contains_text, ensure, equal, unspecified
from mock_upstream import CACHE_USAGE, REPLY, SIGNATURE, THINKING, TOOL_FINAL_REPLY, USAGE

USER_TEXT = "请描述一下长廊。"
BEDROCK_MODEL = "anthropic.claude-sonnet-4-5-20250929-v1:0"
VERTEX_MODEL = "claude-sonnet-4-5@20250929"
MISTRAL_MODEL = "mistral-medium-latest"
# max_tokens 留够空间：思考预算不小于 max_tokens 的问题由 thinking_budget 单独检查，不要盖住其他项
ROOMY_MAX_TOKENS = 16000
# 自适应思考的模型没有预算字段，用来单独测带签名的思考块往返
ADAPTIVE_MODEL = {"bedrock": "anthropic.claude-opus-5-5", "vertex": "claude-opus-5-5", "bedrock_anthropic": "anthropic.claude-opus-5-5"}
AUTH_WORDS = ("token", "令牌", "授权", "鉴权", "认证", "凭据", "服务账号", "service account", "service_account", "credential", "oauth", "jwt", "auth")
ACCOUNT_WORDS = ("服务账号", "api key","service account", "service_account", "client_email", "private_key", "token_uri", "json", "凭据", "credential", "私钥")


@dataclass
class Family:
    key: str
    protocol: str
    model: str
    route: str
    stream_op: str
    once_op: str
    event_stream: bool
    auth_style: str = None
    provider_params: dict = field(default_factory=dict)
    base_suffix: str = ""


FAMILIES = [
    Family("bedrock", "bedrock_converse", BEDROCK_MODEL, "bedrock_converse", "converse-stream", "converse", True),
    Family("mistral", "mistral_conversations", MISTRAL_MODEL, "mistral", "", "", False),
    Family("vertex", "anthropic_messages", VERTEX_MODEL, "vertex", "streamRawPredict", "rawPredict", False,
           auth_style="vertex_service_account", base_suffix="/v1/projects/p/locations/us-east5"),
    Family("bedrock_anthropic", "anthropic_messages", BEDROCK_MODEL, "bedrock_invoke", "invoke-with-response-stream", "invoke", True,
           auth_style="bearer", provider_params={"_host": "bedrock-runtime.invalid"}),
]


def api_key_of(env, fam):
    if fam.key == "vertex":
        return env.fixtures["sa_json"]
    return env.fixtures["mistral_key"] if fam.key == "mistral" else env.fixtures["bedrock_key"]


def preset_for(env, fam, api_key=None):
    preset = {"id": f"check-{fam.key}", "name": f"检查 {fam.key}", "baseUrl": env.mock.url + fam.base_suffix,
              "apiKey": api_key_of(env, fam) if api_key is None else api_key, "models": [fam.model], "protocol": fam.protocol,
              "promptCache": {"mode": "off"}}
    if fam.auth_style:
        preset["authStyle"] = fam.auth_style
    if fam.provider_params:
        preset["providerParams"] = fam.provider_params
    return preset


def prepare(env, fam, fault="ok", stream=True, api_key=None, reasoning="high", max_tokens=ROOMY_MAX_TOKENS, temperature=None, model=None, **mock_options):
    """建预设和新会话，把模拟上游设到指定场景。返回会话 id。"""
    env.put_preset(preset_for(env, fam, api_key))
    env.set_stream(stream)
    env.mock.reset(fault=fault, **mock_options)
    env.mock.api_key = None if fam.key == "vertex" else api_key_of(env, fam)
    env.mock.expect_model = model or fam.model
    return env.new_chat(f"check-{fam.key}", model or fam.model, reasoning=reasoning, max_tokens=max_tokens, temperature=temperature)


def assert_reached(env, fam, result, stream=None):
    """请求必须到达这一家的模拟上游，且没有违反文档。这是控制对照的关键。"""
    mock = env.mock
    calls = mock.calls(fam.route)
    if not calls:
        raise CheckFailed(f"请求没有到达 {fam.key} 的模拟上游。后端：{result.summary()}；模拟上游收到：{mock.requests or '无'}；违规：{mock.violations[:2]}")
    if mock.violations:
        raise CheckFailed(f"模拟上游判定请求不符合文档：{mock.violations[:3]}")
    if stream is not None and fam.stream_op:
        expected = fam.stream_op if stream else fam.once_op
        equal(calls[0].operation, expected, "上游操作")
    if stream is not None and fam.key == "mistral":
        equal(bool((calls[0].json or {}).get("stream")), stream, "Mistral 请求的 stream 字段")
    return calls


def assert_success(env, fam, chat_id, result, stream):
    assert_reached(env, fam, result, stream)
    ensure(not result.hung and not result.transport_error, result.summary())
    ensure(result.succeeded, f"生成应成功：{result.summary()}")
    chat = env.read_chat(chat_id)
    messages = chat["messages"]
    ensure(len(messages) >= 2, f"会话应至少有用户和助手两条消息，实际 {len(messages)} 条")
    equal(messages[-2]["role"], "user", "倒数第二条的 role")
    equal(messages[-2]["content"], USER_TEXT, "用户消息落盘")
    equal(messages[-1]["role"], "assistant", "最后一条的 role")
    return messages[-1]


# ---------- 正向 ----------
def stream_text(fam):
    def run(env):
        chat_id = prepare(env, fam)
        result = env.generate(chat_id, USER_TEXT)
        last = assert_success(env, fam, chat_id, result, True)
        ensure(result.is_sse, f"应是 SSE：{result.summary()}")
        ensure(len(result.of("delta")) >= 2, f"应是真流式，多个 delta，实际 {len(result.of('delta'))} 个")
        equal(result.text, REPLY, "delta 拼接结果")
        equal(result.done.get("chatId"), chat_id, "done.chatId")
        equal(last["content"], REPLY, "助手消息落盘")
        equal(result.done.get("assistantMessageId"), last["id"], "done.assistantMessageId")
        meta = result.done.get("generationMetadata") or {}
        equal(meta.get("protocol"), fam.protocol, "generationMetadata.protocol")
        equal(last.get("generationMetadata", {}).get("protocol"), fam.protocol, "消息 generationMetadata.protocol")
    return run


def once_text(fam):
    def run(env):
        chat_id = prepare(env, fam, stream=False)
        result = env.generate(chat_id, USER_TEXT)
        last = assert_success(env, fam, chat_id, result, False)
        ensure(not result.is_sse, f"streamEnabled=false 时应是 JSON：{result.summary()}")
        equal(result.json.get("chatId"), chat_id, "chatId")
        equal(last["content"], REPLY, "助手消息落盘")
        ensure(contains_text(result.json, REPLY), f"响应体里应有助手正文：{json.dumps(result.json, ensure_ascii=False)[:400]}")
    return run


def _assert_usage(usage, label, total=USAGE["total"]):
    ensure(isinstance(usage, dict), f"{label} 应有 usage：{usage}")
    equal(usage.get("inputTokens"), USAGE["input"], f"{label}.inputTokens")
    equal(usage.get("outputTokens"), USAGE["output"], f"{label}.outputTokens")
    equal(usage.get("totalTokens"), total, f"{label}.totalTokens")


def usage_check(fam, stream):
    def run(env):
        chat_id = prepare(env, fam, stream=stream)
        result = env.generate(chat_id, USER_TEXT)
        last = assert_success(env, fam, chat_id, result, stream)
        _assert_usage(last.get("usage"), "消息 usage")
        _assert_usage((result.done if stream else result.json).get("usage"), "响应 usage")
        summary = env.usage_summary(chat_id)
        equal(summary.get("completedCount"), 1, "账本 completedCount")
        equal(summary.get("inputTokens"), USAGE["input"], "账本 inputTokens")
        equal(summary.get("outputTokens"), USAGE["output"], "账本 outputTokens")
    return run


def cache_usage_check(fam):
    def run(env):
        chat_id = prepare(env, fam, cache_usage=True)
        result = env.generate(chat_id, USER_TEXT)
        last = assert_success(env, fam, chat_id, result, True)
        usage = last.get("usage") or {}
        equal(usage.get("cacheReadInputTokens"), CACHE_USAGE["read"], "cacheReadInputTokens")
        equal(usage.get("cacheWriteInputTokens"), CACHE_USAGE["write"], "cacheWriteInputTokens")
        equal(usage.get("outputTokens"), USAGE["output"], "outputTokens")
    return run


def reasoning_check(fam, stream):
    def run(env):
        chat_id = prepare(env, fam, stream=stream)
        result = env.generate(chat_id, USER_TEXT)
        last = assert_success(env, fam, chat_id, result, stream)
        equal(last.get("reasoningContent"), THINKING, "思考内容落盘")
        equal(last["content"], REPLY, "正文不混入思考")
        if stream:
            equal(result.reasoning, THINKING, "reasoning 事件拼接")
            ensure(THINKING not in result.text, "思考内容不能出现在 delta")
    return run


def _system_text(fam, body):
    if fam.key == "mistral":
        return body.get("instructions") or ""
    if fam.route == "bedrock_converse":
        return " ".join(b.get("text", "") for b in body.get("system") or [])
    system = body.get("system")
    return system if isinstance(system, str) else " ".join(b.get("text", "") for b in system or [])


def _params_of(fam, body):
    if fam.key == "mistral":
        args = body.get("completion_args") or {}
        return args.get("max_tokens"), args.get("temperature")
    if fam.route == "bedrock_converse":
        config = body.get("inferenceConfig") or {}
        return config.get("maxTokens"), config.get("temperature")
    return body.get("max_tokens"), body.get("temperature")


def request_mapping(fam):
    def run(env):
        chat_id = prepare(env, fam, reasoning="none", max_tokens=321, temperature=0.4)
        result = env.generate(chat_id, USER_TEXT)
        assert_success(env, fam, chat_id, result, True)
        body = env.mock.calls(fam.route)[0].json
        ensure("SYSMARKER-角色设定" in _system_text(fam, body), f"角色设定应走协议的系统提示字段：{json.dumps(body, ensure_ascii=False)[:400]}")
        equal(_params_of(fam, body), (321, 0.4), "max_tokens 和 temperature 的映射")
        ensure(USER_TEXT in json.dumps(body, ensure_ascii=False), "请求里应有用户消息")
    return run


def _history_blob(fam, body):
    return json.dumps(body.get("inputs") if fam.key == "mistral" else body.get("messages"), ensure_ascii=False)


def _reasoning_blocks(fam, body):
    if fam.key == "mistral":
        return []
    found = []
    for message in body.get("messages", []):
        if isinstance(message.get("content"), list):
            for block in message["content"]:
                if fam.route == "bedrock_converse" and "reasoningContent" in block:
                    text = block["reasoningContent"].get("reasoningText") or {}
                    found.append((text.get("text"), text.get("signature")))
                elif block.get("type") == "thinking":
                    found.append((block.get("thinking"), block.get("signature")))
    return found


def history_check(fam):
    def run(env):
        chat_id = prepare(env, fam)
        first = env.generate(chat_id, USER_TEXT)
        assert_success(env, fam, chat_id, first, True)
        env.mock.reset()
        env.mock.api_key = None if fam.key == "vertex" else api_key_of(env, fam)
        env.mock.expect_model = fam.model
        second = env.generate(chat_id, "接着说。")
        assert_reached(env, fam, second, True)
        ensure(second.succeeded, second.summary())
        body = env.mock.calls(fam.route)[0].json
        blob = _history_blob(fam, body)
        ensure(USER_TEXT in blob and REPLY.split("\n")[0][:6] in blob and "接着说。" in blob, f"第二轮请求应带上历史：{blob[:400]}")
        ensure(blob.index(USER_TEXT) < blob.index("接着说。"), "历史顺序不对")
        for text, signature in _reasoning_blocks(fam, body):
            equal(text, THINKING, "回传思考内容应原样")
            equal(signature, SIGNATURE, "回传思考签名应原样")
    return run


def forward_compat_check(fam):
    def run(env):
        chat_id = prepare(env, fam, forward_compat=True)
        result = env.generate(chat_id, USER_TEXT)
        assert_success(env, fam, chat_id, result, True)
        equal(result.text, REPLY, "遇到不认识的事件后，文字仍应完整")
    return run


def _run_tool_round(env, fam, reasoning, model):
    env.put_preset(preset_for(env, fam))
    env.set_stream(True)
    env.api.json_ok("PUT", "/api/assistant/settings", json={"presetId": f"check-{fam.key}", "model": model, "reasoningEffort": reasoning})
    env.api.json_ok("POST", "/api/assistant/reset", params={"scope": "workspace"})
    mock = env.mock
    mock.reset(tool_round=True)
    mock.api_key = None if fam.key == "vertex" else api_key_of(env, fam)
    mock.expect_model = model
    result = env.api.stream("/api/assistant/stream", {"userMessage": "看一下现有内容。", "scope": "workspace", "model": model}, deadline=60.0)
    calls = assert_reached(env, fam, result)
    ensure(mock.tool_used, f"请求里应带工具定义：{result.summary()}")
    ensure(len(calls) >= 2, f"工具结果应再发一轮，实际 {len(calls)} 轮；后端：{result.summary()}")
    ensure(result.succeeded, f"工具往返应成功：{result.summary()}")
    ensure(TOOL_FINAL_REPLY in result.text, f"最后的回答应流给前端：{result.text[:200]!r}")
    chat = env.api.json_ok("GET", "/api/assistant/chat", params={"scope": "workspace"})
    ensure(any(m.get("role") == "assistant" and TOOL_FINAL_REPLY in (m.get("content") or "") for m in chat["messages"]), "最后的回答应落盘到助手会话")
    return calls


def tool_round_check(fam):
    def run(env):
        _run_tool_round(env, fam, "none", fam.model)
    return run


def tool_round_signed_check(fam):
    def run(env):
        calls = _run_tool_round(env, fam, "high", ADAPTIVE_MODEL[fam.key])
        if not env.mock.tool_reasoning_sent:
            ensure(fam.route == "bedrock_converse", "思考档位 high 时，Anthropic 请求应带 thinking")
            unspecified("Converse 请求没有 additionalModelRequestFields.thinking，所以这一轮模拟上游没有返回思考块（产品规格没写 Converse 如何映射思考档位）")
        blocks = _reasoning_blocks(fam, calls[-1].json)
        ensure(blocks, "工具往返要回传带签名的思考块，第二轮请求里没有")
        equal(blocks[0], (THINKING, SIGNATURE), "思考块应原样回传")
    return run


def thinking_budget_check(fam):
    def run(env):
        chat_id = prepare(env, fam, reasoning="medium", max_tokens=None)
        result = env.generate(chat_id, USER_TEXT)
        calls = env.mock.calls(fam.route)
        ensure(calls, f"请求没有到达 {fam.key} 的模拟上游：{result.summary()}；违规：{env.mock.violations[:2]}")
        body = calls[0].json
        thinking = body.get("thinking") or {}
        if thinking.get("type") == "enabled":
            ensure(thinking.get("budget_tokens", 0) < body.get("max_tokens", 0), f"文档要求 budget_tokens 小于 max_tokens：budget={thinking.get('budget_tokens')} max_tokens={body.get('max_tokens')}")
        assert_success(env, fam, chat_id, result, True)
    return run


def greeting_first_check(fam):
    def run(env):
        prepare(env, fam, reasoning="none")
        character = env.api.json_ok("POST", "/api/characters", json={"name": "有开场白的角色", "description": "d", "firstMessage": "GREETING-你来了。"})
        chat = env.api.json_ok("POST", "/api/chats", json={"characterId": character["id"]})
        equal(chat["messages"][0]["role"], "assistant", "会话以开场白开始")
        env.api.json_ok("PUT", f"/api/chats/{chat['id']}", json={"overrides": {"presetId": f"check-{fam.key}", "params": {"model": fam.model, "reasoningEffort": "none"}}})
        result = env.generate(chat["id"], USER_TEXT)
        assert_success(env, fam, chat["id"], result, True)
        ensure("GREETING-你来了。" in json.dumps(env.mock.calls(fam.route)[0].json, ensure_ascii=False), "开场白应作为上下文发给上游")
    return run


def system_message_check(fam):
    def run(env):
        chat_id = prepare(env, fam, reasoning="none")
        env.api.json_ok("POST", f"/api/chats/{chat_id}/messages", json={"role": "user", "content": "前一条用户消息"})
        env.api.json_ok("POST", f"/api/chats/{chat_id}/messages", json={"role": "assistant", "content": "前一条回复"})
        env.api.json_ok("POST", f"/api/chats/{chat_id}/messages", json={"role": "system", "content": "MIDSYSTEM-旁白"})
        result = env.generate(chat_id, USER_TEXT)
        assert_success(env, fam, chat_id, result, True)
        ensure("MIDSYSTEM-旁白" in json.dumps(env.mock.calls(fam.route)[0].json, ensure_ascii=False), "会话里的系统消息不能丢")
    return run


def draft_help_check(fam):
    def run(env):
        chat_id = prepare(env, fam, reasoning="none")
        before = env.read_chat(chat_id)["messages"]
        result = env.api.stream("/api/generate/draft-help", {"chatId": chat_id, "mode": "write"}, deadline=60.0)
        assert_reached(env, fam, result)
        ensure(result.succeeded, f"写作辅助应成功：{result.summary()}")
        equal(result.text, REPLY, "写作辅助文字")
        equal(env.read_chat(chat_id)["messages"], before, "写作辅助不写会话")
    return run


def group_check(fam):
    def run(env):
        prepare(env, fam, reasoning="none")
        character = env.ensure_character()
        group = env.api.json_ok("POST", "/api/chats", json={"characterId": character, "isGroup": True, "memberIds": [character], "title": "检查群聊"})
        env.api.json_ok("PUT", f"/api/chats/{group['id']}", json={"overrides": {"presetId": f"check-{fam.key}", "params": {"model": fam.model, "reasoningEffort": "none"}}})
        result = env.api.stream("/api/generate/group", {"chatId": group["id"], "characterId": character}, deadline=60.0)
        assert_reached(env, fam, result)
        ensure(result.succeeded, f"群聊生成应成功：{result.summary()}")
        equal(result.done.get("characterId"), character, "done.characterId")
        last = env.read_chat(group["id"])["messages"][-1]
        equal(last["content"], REPLY, "群聊助手消息落盘")
    return run


# ---------- 负向 ----------
def assert_failure(env, fam, chat_id, result, stream, status=None):
    assert_reached(env, fam, result)
    ensure(not result.hung, result.summary())
    ensure(not result.transport_error, f"应以结构化错误结束，而不是断开：{result.summary()}")
    ensure(not result.succeeded, f"不能当成成功：{result.summary()}")
    error = result.error
    ensure(error, f"应有错误信封：{result.summary()}")
    for key in ("code", "message", "requestId"):
        ensure(isinstance(error.get(key), str) and error[key], f"错误缺少 {key}：{json.dumps(error, ensure_ascii=False)[:300]}")
    ensure(error["code"] != "provider_capability_unsupported", f"不应再是能力不支持的快速失败：{error['code']}")
    if result.is_sse:
        equal(error.get("terminal"), True, "SSE 错误的 terminal")
        ensure(not result.of("done"), "出现 error 后不能再发 done")
    if status is not None and error.get("upstreamStatus") is not None:
        equal(error["upstreamStatus"], status, "upstreamStatus")
    messages = env.read_chat(chat_id)["messages"]
    ensure(any(m["role"] == "user" and m["content"] == USER_TEXT for m in messages), "失败后用户消息不能丢")
    equal(env.usage_summary(chat_id).get("completedCount"), 0, "失败不能计入 completedCount")
    return error, messages


def http_error_check(fam, status, stream):
    def run(env):
        chat_id = prepare(env, fam, fault=f"http_{status}", stream=stream)
        result = env.generate(chat_id, USER_TEXT)
        error, messages = assert_failure(env, fam, chat_id, result, stream, status)
        if status in (401, 403):
            equal(error["code"], "provider_auth_failed", "鉴权失败的 code")
            equal(error.get("retryable"), False, "鉴权失败的 retryable")
        else:
            ensure(error["code"] != "provider_auth_failed", f"{status} 不应映射成鉴权失败")
            equal(error.get("retryable"), True, f"{status} 的 retryable")
        ensure(not any(m["role"] == "assistant" and "mock" in (m.get("content") or "") for m in messages), "错误文字不能写成助手消息")
    return run


def stream_fault_check(fam, fault):
    def run(env):
        chat_id = prepare(env, fam, fault=fault)
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        _error, messages = assert_failure(env, fam, chat_id, result, True)
        ensure("不应出现的文字" not in result.text, "CRC 错误的帧不能被当成正文")
        for message in messages:
            ensure("不应出现的文字" not in (message.get("content") or ""), "CRC 错误的帧不能落盘")
            if message["role"] == "assistant":
                ensure((message.get("generationMetadata") or {}).get("status") != "completed", "残缺结果不能标为 completed")
    return run


def once_fault_check(fam, fault):
    def run(env):
        chat_id = prepare(env, fam, fault=fault, stream=False)
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        assert_failure(env, fam, chat_id, result, False)
    return run


# ---------- 密钥 ----------
def _secrets(env, fam, extra=()):
    found = list(extra)
    if fam.key == "vertex":
        found += fixtures.private_key_fragments(env.fixtures["pem"])
        found += env.mock.issued_tokens
        if env.mock.last_assertion:
            found.append(env.mock.last_assertion)
    else:
        found.append(api_key_of(env, fam))
    return [s for s in found if s]


def _surfaces(env, chat_id, result):
    api = env.api
    surfaces = {"生成响应": result.raw.decode("utf-8", "replace")}
    if chat_id:
        surfaces["会话"] = api.get(f"/api/chats/{chat_id}").text
        surfaces["会话导出"] = api.get(f"/api/chats/{chat_id}/export", params={"format": "json"}).text
        surfaces["账本事件"] = api.get("/api/usage/events", params={"scope": "chat", "chatId": chat_id}).text
    log_list = api.get("/api/http-log")
    surfaces["HTTP 日志列表"] = log_list.text
    details = []
    for item in log_list.json().get("items", []):
        record_id = item.get("id") or item.get("recordId")
        if record_id:
            details.append(api.get(f"/api/http-log/{record_id}").text)
    surfaces["HTTP 日志详情"] = "\n".join(details)
    if env.log_path:
        with open(env.log_path, encoding="utf-8", errors="replace") as f:
            surfaces["后端日志"] = f.read()
    return surfaces


def assert_no_secrets(env, fam, chat_id, result, require_log=True, extra=()):
    deadline = time.time() + 5
    while True:
        surfaces = _surfaces(env, chat_id, result)
        if not require_log or surfaces["HTTP 日志详情"] or time.time() > deadline:
            break
        time.sleep(0.2)
    if require_log:
        ensure(surfaces["HTTP 日志详情"], "HTTP 日志里没有这次请求的记录，密钥检查会落空")
    secrets = _secrets(env, fam, extra)
    ensure(secrets, "没有可扫描的密钥，检查会落空")
    leaks = [f"{surface} 含第 {i + 1} 项密钥（{secret[:12]}…）" for surface, text in surfaces.items() for i, secret in enumerate(secrets) if secret in text]
    ensure(not leaks, "；".join(leaks[:6]))


def secrets_success(fam, stream):
    def run(env):
        chat_id = prepare(env, fam, stream=stream)
        env.api.json_ok("DELETE", "/api/http-log")
        result = env.generate(chat_id, USER_TEXT)
        assert_success(env, fam, chat_id, result, stream)
        assert_no_secrets(env, fam, chat_id, result)
    return run


def secrets_echo(fam, status):
    def run(env):
        chat_id = prepare(env, fam, fault=f"http_{status}", echo_secret=True)
        env.api.json_ok("DELETE", "/api/http-log")
        result = env.generate(chat_id, USER_TEXT)
        assert_failure(env, fam, chat_id, result, True, status)
        assert_no_secrets(env, fam, chat_id, result)
    return run


# ---------- Bedrock 专有 ----------
def bedrock_arn_model(env):
    fam = FAMILIES[0]
    arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    chat_id = prepare(env, fam, model=arn)
    result = env.generate(chat_id, USER_TEXT)
    calls = env.mock.calls(fam.route)
    ensure(calls, f"推理配置文件 ARN 含斜杠和冒号，要整体编码成一个路径段。上游收到：{env.mock.requests}；违规：{env.mock.violations[:2]}；后端：{result.summary()}")
    assert_success(env, fam, chat_id, result, True)


# ---------- Mistral 专有 ----------
def mistral_base_with_v1(env):
    fam = FAMILIES[1]
    chat_id = prepare(env, fam)
    preset = preset_for(env, fam)
    preset["baseUrl"] = env.mock.url + "/v1"
    env.put_preset(preset)
    result = env.generate(chat_id, USER_TEXT)
    ensure(env.mock.calls(fam.route), f"baseUrl 带 /v1 时也应请求 /v1/conversations。上游收到：{env.mock.requests}；后端：{result.summary()}")
    assert_success(env, fam, chat_id, result, True)


def mistral_store_note(env):
    fam = FAMILIES[1]
    chat_id = prepare(env, fam)
    result = env.generate(chat_id, USER_TEXT)
    assert_success(env, fam, chat_id, result, True)
    store = env.mock.calls(fam.route)[0].json.get("store", "未发送")
    unspecified(f"Conversations 请求的 store 字段是 {store}（文档：决定是否存到 Mistral 服务器；产品规格没说应取什么）")


# ---------- Vertex 专有 ----------
def vertex_jwt_exchange(env):
    fam = FAMILIES[2]
    chat_id = prepare(env, fam)
    result = env.generate(chat_id, USER_TEXT)
    assert_success(env, fam, chat_id, result, True)
    mock = env.mock
    ensure(mock.token_requests, "应向 token_uri 换 token")
    ensure(mock.issued_tokens, "token 端点应已发出 token")
    auth = mock.calls("vertex")[0].headers.get("Authorization")
    equal(auth, f"Bearer {mock.issued_tokens[-1]}", "Vertex 请求的 Authorization")


def vertex_token_reuse_note(env):
    fam = FAMILIES[2]
    chat_id = prepare(env, fam)
    first = env.generate(chat_id, USER_TEXT)
    assert_success(env, fam, chat_id, first, True)
    count_after_first = len(env.mock.token_requests)
    second = env.generate(chat_id, "接着说。")
    assert_reached(env, fam, second, True)
    unspecified(f"两次生成共换 token {len(env.mock.token_requests)} 次，第一次之后 {count_after_first} 次（Google 文档说 token 可复用到过期，但没有要求必须缓存）")


def _sa_variant(env, mutate):
    info = json.loads(env.fixtures["sa_json"])
    mutate(info)
    return json.dumps(info, ensure_ascii=False)


def sa_invalid_check(make_key, words=ACCOUNT_WORDS, may_hit_token=False):
    def run(env):
        fam = FAMILIES[2]
        api_key = make_key(env)
        chat_id = prepare(env, fam, api_key=api_key)
        env.api.json_ok("DELETE", "/api/http-log")
        result = env.generate(chat_id, USER_TEXT, deadline=30.0)
        ensure(not env.mock.calls("vertex"), f"服务账号有问题时不该调 Vertex。上游收到：{env.mock.requests}；后端：{result.summary()}")
        if not may_hit_token:
            ensure(not env.mock.requests, f"服务账号有问题时不该发出任何请求。上游收到：{env.mock.requests}；后端：{result.summary()}")
        ensure(not env.mock.proxy_attempts, f"不该访问外网：{env.mock.proxy_attempts}")
        ensure(not result.hung and not result.transport_error, result.summary())
        ensure(not result.succeeded, f"不能当成成功：{result.summary()}")
        error = result.error
        ensure(error, f"应有错误信封：{result.summary()}")
        for key in ("code", "message", "requestId"):
            ensure(isinstance(error.get(key), str) and error[key], f"错误缺少 {key}：{str(error)[:300]}")
        text = f"{error.get('message')} {error.get('detail')}".lower()
        ensure(any(word in text for word in words), f"错误应明确指向服务账号配置：{text[:200]}")
        ensure("-----begin" not in text and "private key-----" not in text, "错误里不能带私钥")
        scan = result.raw.decode("utf-8", "replace")
        for fragment in fixtures.private_key_fragments(env.fixtures["pem"])[:3]:
            ensure(fragment not in scan, "响应里不能带私钥")
    return run


def token_fault_check(fault):
    def run(env):
        fam = FAMILIES[2]
        chat_id = prepare(env, fam, token_fault=fault)
        env.api.json_ok("DELETE", "/api/http-log")
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        ensure(env.mock.token_requests, f"应先请求 token 端点。上游收到：{env.mock.requests}；后端：{result.summary()}")
        ensure(not env.mock.calls("vertex"), "token 失败时不该继续调 Vertex")
        ensure(not env.mock.violations, f"JWT 不符合文档：{env.mock.violations[:2]}")
        ensure(not result.hung and not result.transport_error, result.summary())
        ensure(not result.succeeded, f"不能当成成功：{result.summary()}")
        error = result.error
        ensure(error, f"应有错误信封：{result.summary()}")
        for key in ("code", "message", "requestId"):
            ensure(isinstance(error.get(key), str) and error[key], f"错误缺少 {key}：{str(error)[:300]}")
        text = f"{error.get('code')} {error.get('message')} {error.get('detail')}".lower()
        ensure(any(word in text for word in AUTH_WORDS), f"错误应指向取 token 失败：{text[:200]}")
        messages = env.read_chat(chat_id)["messages"]
        ensure(any(m["role"] == "user" and m["content"] == USER_TEXT for m in messages), "失败后用户消息不能丢")
        if fault == "invalid_grant_echo":
            assert_no_secrets(env, fam, chat_id, result, require_log=False)
    return run


def no_external_network(env):
    hosts = [h for h in env.mock.proxy_attempts if any(word in h for word in ("amazonaws", "googleapis", "mistral", "anthropic", "bedrock"))]
    ensure(not hosts, f"运行中有发往外网模型服务的请求：{hosts}")


# ---------- 注册 ----------
for _fam in FAMILIES:
    _p = f"t832.{_fam.key}"
    add_check(f"{_p}.stream.text", "流式文字完整、顺序正确、落盘到会话", stream_text(_fam))
    add_check(f"{_p}.once.text", "非流式文字完整并落盘", once_text(_fam))
    add_check(f"{_p}.stream.usage", "流式用量归一化，写入消息和账本", usage_check(_fam, True))
    add_check(f"{_p}.once.usage", "非流式用量归一化，写入消息和账本", usage_check(_fam, False))
    add_check(f"{_p}.stream.reasoning", "流式思考内容和正文分开", reasoning_check(_fam, True))
    add_check(f"{_p}.once.reasoning", "非流式思考内容和正文分开", reasoning_check(_fam, False))
    add_check(f"{_p}.request_mapping", "系统提示、max_tokens、temperature 映射到协议字段", request_mapping(_fam))
    add_check(f"{_p}.history", "第二轮带历史；回传思考时文字和签名原样", history_check(_fam))
    add_check(f"{_p}.forward_compat", "遇到不认识的事件不影响文字", forward_compat_check(_fam))
    add_check(f"{_p}.tool_round", "助手工具往返：工具定义、调用、结果回传、最后回答落盘", tool_round_check(_fam))
    add_check(f"{_p}.greeting_first", "会话以开场白开始时，发给上游的第一条仍符合文档", greeting_first_check(_fam))
    add_check(f"{_p}.system_message", "会话中间有系统消息时，不用文档不允许的 role，也不丢内容", system_message_check(_fam))
    if _fam.key != "mistral":
        add_check(f"{_p}.tool_round_signed", "思考开启时，工具往返原样回传带签名的思考块", tool_round_signed_check(_fam))
    if _fam.key in ("vertex", "bedrock_anthropic"):
        add_check(f"{_p}.thinking_budget", "默认 max_tokens 加思考档位时，budget_tokens 小于 max_tokens", thinking_budget_check(_fam))
    add_check(f"{_p}.draft_help", "写作辅助走同一协议，不写会话", draft_help_check(_fam))
    add_check(f"{_p}.group", "群聊生成走同一协议", group_check(_fam))
    if _fam.key != "mistral":
        add_check(f"{_p}.stream.cache_usage", "缓存读写用量归一化", cache_usage_check(_fam))
    for _status in (401, 403, 429, 500, 503):
        add_check(f"{_p}.stream.http_{_status}", f"流式上游 {_status} 映射为结构化错误", http_error_check(_fam, _status, True))
    for _status in (401, 403, 429, 500):
        add_check(f"{_p}.once.http_{_status}", f"非流式上游 {_status} 映射为结构化错误", http_error_check(_fam, _status, False))
    _faults = ["truncate", "no_terminal", "malformed_json", "exception_event"]
    if _fam.event_stream:
        _faults += ["truncate_prelude", "bad_prelude_crc", "bad_message_crc", "exception_internal", "unmodeled_error"]
    for _fault in _faults:
        add_check(f"{_p}.stream.{_fault}", f"流式故障 {_fault} 不算成功、不悬挂", stream_fault_check(_fam, _fault))
    for _fault in ("malformed_json", "truncate", "empty_output"):
        add_check(f"{_p}.once.{_fault}", f"非流式故障 {_fault} 不算成功、不悬挂", once_fault_check(_fam, _fault))
    add_check(f"{_p}.secrets.stream", "流式成功后，响应、会话、账本、HTTP 日志、后端日志都没有密钥", secrets_success(_fam, True))
    add_check(f"{_p}.secrets.once", "非流式成功后同样没有密钥", secrets_success(_fam, False))
    add_check(f"{_p}.secrets.error_echo", "上游错误信息回显凭据时，错误详情和日志里也没有", secrets_echo(_fam, 401))

add_check("t832.bedrock.model_arn", "推理配置文件 ARN 整体编码成一个路径段", bedrock_arn_model)
add_check("t832.mistral.base_url_v1", "目录模板的 baseUrl 带 /v1 时不会变成 /v1/v1", mistral_base_with_v1)
add_check("t832.mistral.store_note", "记录 store 字段取值", mistral_store_note)
add_check("t832.vertex.jwt_exchange", "用服务账号 JWT 换 token，并用它调用 Vertex；JWT 的签名和声明都通过校验", vertex_jwt_exchange)
add_check("t832.vertex.token_reuse_note", "记录是否复用 token", vertex_token_reuse_note)
add_check("t832.vertex.sa.not_json", "服务账号不是 JSON 时明确报错", sa_invalid_check(lambda env: "{not json, \"private_key\": \"-----BEGIN PRIVATE KEY-----abc"))
add_check("t832.vertex.sa.json_array", "服务账号 JSON 不是对象时明确报错", sa_invalid_check(lambda env: "[1, 2]"))
add_check("t832.vertex.sa.empty", "服务账号为空时明确报错", sa_invalid_check(lambda env: ""))
for _field in ("client_email", "private_key", "token_uri"):
    add_check(f"t832.vertex.sa.missing_{_field}", f"缺少 {_field} 时明确报错，不发请求",
              sa_invalid_check(lambda env, f=_field: _sa_variant(env, lambda info: info.pop(f))))
add_check("t832.vertex.sa.bad_private_key", "私钥解析失败时明确报错，不回显私钥",
          sa_invalid_check(lambda env: _sa_variant(env, lambda info: info.update(private_key="-----BEGIN PRIVATE KEY-----\nbm90LWEta2V5\n-----END PRIVATE KEY-----\n"))))
add_check("t832.vertex.sa.wrong_type", "type 不是 service_account 时明确报错",
          sa_invalid_check(lambda env: _sa_variant(env, lambda info: info.update(type="authorized_user"))))
for _fault in ("invalid_grant", "http_500", "not_json", "no_access_token", "drop", "invalid_grant_echo"):
    add_check(f"t832.vertex.token.{_fault}", f"token 端点故障 {_fault} 时明确报错，不调 Vertex", token_fault_check(_fault))
add_check("t832.no_external_network", "这一组运行期间没有发往外网模型服务的请求", no_external_network)
