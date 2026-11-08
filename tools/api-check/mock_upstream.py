"""模拟上游：Bedrock、Mistral、Vertex、Google token 端点，加上现有协议的对照路由。

只照官方文档写，不看产品实现。文档地址见 README.md。
- 请求不符合文档时，把问题记进 violations，并按该服务的错误格式返回 400 或 401。
- 所有请求都记进 requests，检查据此判断请求到底有没有到上游。
- 一次只服务一个场景，由检查在发请求前用 reset() 设定。
"""
import base64
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import eventstream as es
import jwt

THINKING_CHUNKS = ["先想一想语气，", "再决定要不要", "留一个钩子。"]
REPLY_CHUNKS = ["第一段：灯光落在", "长廊尽头。", "\n\n第二段：他回头", "看了看，", "没有说话。🙂"]
THINKING = "".join(THINKING_CHUNKS)
REPLY = "".join(REPLY_CHUNKS)
TOOL_FINAL_REPLY = "工具结果已收到，这是最后的回答。"
SIGNATURE = "c2lnbmF0dXJlLWZyb20tbW9jaw=="
USAGE = {"input": 11, "output": 7, "total": 18}
CACHE_USAGE = {"read": 5, "write": 3}
BEDROCK_TOP_KEYS = {"additionalModelRequestFields", "additionalModelResponseFieldPaths", "guardrailConfig", "inferenceConfig",
                    "messages", "outputConfig", "performanceConfig", "promptVariables", "requestMetadata", "serviceTier", "system", "toolConfig"}
BEDROCK_INFERENCE_KEYS = {"maxTokens", "stopSequences", "temperature", "topP"}
BEDROCK_BLOCKS = {"audio", "cachePoint", "citationsContent", "document", "guardContent", "image", "reasoningContent",
                  "searchResult", "text", "toolResult", "toolUse", "video"}
MISTRAL_TOP_KEYS = {"inputs", "stream", "store", "handoff_execution", "instructions", "tools", "completion_args", "guardrails",
                    "name", "description", "metadata", "agent_id", "agent_version", "model"}
MISTRAL_COMPLETION_KEYS = {"stop", "presence_penalty", "frequency_penalty", "temperature", "top_p", "max_tokens", "random_seed",
                           "prediction", "response_format", "tool_choice", "reasoning_effort"}
TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
GOOGLE_TOKEN_AUD = "https://oauth2.googleapis.com/token"
CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
ANTHROPIC_VERSION = {"vertex": "vertex-2023-10-16", "bedrock": "bedrock-2023-05-31"}


class Recorded:
    def __init__(self, method, path, headers, raw):
        self.method, self.path, self.headers, self.raw = method, path, headers, raw
        self.route = ""
        self.operation = ""
        try:
            self.json = json.loads(raw) if raw else None
        except ValueError:
            self.json = None

    def __repr__(self):
        return f"{self.method} {self.path}"


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """客户端断开是这里的常态，不打印堆栈。"""


class MockUpstream:
    def __init__(self, port):
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.token_uri = f"{self.url}/oauth2/token"
        self.lock = threading.Lock()
        self.api_key = None
        self.service_account = None
        self.public_key = None
        self.expect_model = None
        self.issued_tokens = []
        self.proxy_attempts = []
        self.reset()
        self.server = _QuietServer(("127.0.0.1", port), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def reset(self, fault="ok", token_fault="ok", tool_round=False, cache_usage=False, echo_secret=None, forward_compat=False):
        with self.lock:
            self.fault = fault
            self.token_fault = token_fault
            self.tool_round = tool_round
            self.cache_usage = cache_usage
            self.echo_secret = echo_secret
            self.forward_compat = forward_compat
            self.requests = []
            self.violations = []
            self.token_requests = []
            self.last_assertion = None
            self.tool_used = None
            self.tool_reasoning_sent = False

    def calls(self, *routes):
        return [r for r in self.requests if r.route in routes]

    def _handler(mock):
        class Handler(_UpstreamHandler):
            upstream = mock

        return Handler


def _bearer(headers):
    value = headers.get("Authorization") or ""
    return value[7:] if value.startswith("Bearer ") else None


def _one_key(block):
    return isinstance(block, dict) and len(block) == 1


# ---------- 按文档校验请求 ----------
def validate_converse(body):
    """API_runtime_Converse / ConverseStream 的请求结构。"""
    if not isinstance(body, dict):
        return ["请求体不是 JSON 对象"]
    bad = [f"顶层字段 {k} 不在 Converse 文档里" for k in body if k not in BEDROCK_TOP_KEYS]
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return bad + ["messages 必须是非空数组"]
    if messages[0].get("role") != "user":
        bad.append("第一条消息必须是 user")
    used = set()
    for i, message in enumerate(messages):
        if message.get("role") not in ("user", "assistant"):
            bad.append(f"messages[{i}].role 只能是 user 或 assistant：{message.get('role')!r}")
        content = message.get("content")
        if not isinstance(content, list) or not content:
            bad.append(f"messages[{i}].content 必须是非空数组")
            continue
        for block in content:
            if not _one_key(block) or next(iter(block)) not in BEDROCK_BLOCKS:
                bad.append(f"messages[{i}] 的内容块必须是联合类型，只有一个成员：{str(block)[:80]}")
                continue
            if "text" in block and not isinstance(block["text"], str):
                bad.append(f"messages[{i}] 的 text 必须是字符串")
            if "toolUse" in block:
                use = block["toolUse"]
                if not (isinstance(use, dict) and use.get("toolUseId") and use.get("name") and isinstance(use.get("input"), dict)):
                    bad.append(f"toolUse 需要 toolUseId、name 和对象形式的 input：{str(use)[:120]}")
                else:
                    used.add(use["toolUseId"])
            if "toolResult" in block:
                result = block["toolResult"]
                if not (isinstance(result, dict) and isinstance(result.get("content"), list) and result.get("toolUseId")):
                    bad.append(f"toolResult 需要 toolUseId 和数组形式的 content：{str(result)[:120]}")
                elif result["toolUseId"] not in used:
                    bad.append(f"toolResult.toolUseId 前面没有对应的 toolUse：{result['toolUseId']}")
                elif "status" in result and result["status"] not in ("success", "error"):
                    bad.append(f"toolResult.status 只能是 success 或 error：{result['status']}")
            if "reasoningContent" in block:
                reasoning = block["reasoningContent"]
                if not _one_key(reasoning) or next(iter(reasoning)) not in ("reasoningText", "redactedContent"):
                    bad.append("reasoningContent 必须是 reasoningText 或 redactedContent")
                elif "reasoningText" in reasoning and not isinstance(reasoning["reasoningText"].get("text"), str):
                    bad.append("reasoningText.text 必须是字符串")
    system = body.get("system")
    if system is not None:
        if not isinstance(system, list):
            bad.append("system 必须是数组")
        else:
            for block in system:
                if not _one_key(block):
                    bad.append("system 内容块必须是联合类型")
                elif "text" in block and (not isinstance(block["text"], str) or not block["text"]):
                    bad.append("system 的 text 长度至少为 1")
    config = body.get("inferenceConfig")
    if config is not None:
        if not isinstance(config, dict):
            bad.append("inferenceConfig 必须是对象")
        else:
            bad += [f"inferenceConfig.{k} 不在文档里" for k in config if k not in BEDROCK_INFERENCE_KEYS]
            if "maxTokens" in config and (not isinstance(config["maxTokens"], int) or config["maxTokens"] < 1):
                bad.append("inferenceConfig.maxTokens 必须是正整数")
            for key in ("temperature", "topP"):
                if key in config and not (isinstance(config[key], (int, float)) and 0 <= config[key] <= 1):
                    bad.append(f"inferenceConfig.{key} 必须在 0 到 1 之间")
    tools = body.get("toolConfig")
    if tools is not None:
        if not isinstance(tools, dict) or not isinstance(tools.get("tools"), list) or not tools["tools"]:
            bad.append("toolConfig.tools 必须是非空数组")
        else:
            for tool in tools["tools"]:
                if "cachePoint" in tool:
                    continue
                spec = tool.get("toolSpec") if isinstance(tool, dict) else None
                if not isinstance(spec, dict) or not TOOL_NAME.match(str(spec.get("name"))):
                    bad.append(f"toolSpec.name 不符合 [a-zA-Z0-9_-]{{1,64}}：{str(tool)[:80]}")
                    continue
                schema = spec.get("inputSchema")
                if not _one_key(schema) or not isinstance(schema.get("json"), dict):
                    bad.append(f"toolSpec.inputSchema 必须是 {{json: 对象}}：{spec.get('name')}")
                if "description" in spec and not spec["description"]:
                    bad.append(f"toolSpec.description 长度至少为 1：{spec.get('name')}")
    return bad


def _validate_anthropic_blocks(content, index, bad, tool_ids):
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        bad.append(f"messages[{index}].content 必须是字符串或内容块数组")
        return
    for block in content:
        kind = block.get("type") if isinstance(block, dict) else None
        if not kind:
            bad.append(f"messages[{index}] 的内容块缺少 type：{str(block)[:80]}")
        elif kind == "text" and not isinstance(block.get("text"), str):
            bad.append(f"messages[{index}] 的 text 块缺少 text")
        elif kind == "tool_use":
            if not (block.get("id") and block.get("name") and isinstance(block.get("input"), dict)):
                bad.append("tool_use 需要 id、name 和对象形式的 input")
            else:
                tool_ids.add(block["id"])
        elif kind == "tool_result" and block.get("tool_use_id") not in tool_ids:
            bad.append(f"tool_result.tool_use_id 前面没有对应的 tool_use：{block.get('tool_use_id')}")
        elif kind == "thinking" and not (isinstance(block.get("thinking"), str) and block.get("signature")):
            bad.append("thinking 块回传时要带 thinking 和 signature")


def validate_anthropic(body, variant, stream):
    """Vertex 和 Bedrock 上的 Anthropic Messages：anthropic_version 放在请求体，模型在 URL 里，请求体没有 model。"""
    if not isinstance(body, dict):
        return ["请求体不是 JSON 对象"]
    bad = []
    expected = ANTHROPIC_VERSION[variant]
    if body.get("anthropic_version") != expected:
        bad.append(f"anthropic_version 必须是 {expected}：{body.get('anthropic_version')!r}")
    if "model" in body:
        bad.append("请求体不能有 model，模型在 URL 里")
    if variant == "vertex":
        if stream and body.get("stream") is not True:
            bad.append("streamRawPredict 的请求体要有 stream=true")
        if not stream and body.get("stream") not in (None, False):
            bad.append("rawPredict 的请求体不能是 stream=true")
    elif "stream" in body:
        bad.append("Bedrock Invoke 的请求体字段里没有 stream，流式由接口路径决定")
    if not isinstance(body.get("max_tokens"), int) or body["max_tokens"] < 1:
        bad.append("max_tokens 必填且为正整数")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return bad + ["messages 必须是非空数组"]
    if messages[0].get("role") != "user":
        bad.append("第一条消息必须是 user")
    tool_ids = set()
    for i, message in enumerate(messages):
        if message.get("role") not in ("user", "assistant"):
            bad.append(f"messages[{i}].role 只能是 user 或 assistant：{message.get('role')!r}")
        _validate_anthropic_blocks(message.get("content"), i, bad, tool_ids)
    system = body.get("system")
    if system is not None and not isinstance(system, (str, list)):
        bad.append("system 必须是字符串或内容块数组")
    thinking = body.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        budget = thinking.get("budget_tokens")
        if not isinstance(budget, int) or budget < 1024 or budget >= body.get("max_tokens", 0):
            bad.append(f"thinking.budget_tokens 至少 1024 且小于 max_tokens：{budget}")
    for tool in body.get("tools") or []:
        if not TOOL_NAME.match(str(tool.get("name"))) or not isinstance(tool.get("input_schema"), dict):
            bad.append(f"tools 的每一项需要 name 和 input_schema：{str(tool)[:80]}")
    return bad


def validate_mistral(body, expect_model):
    """Mistral POST /v1/conversations。"""
    if not isinstance(body, dict):
        return ["请求体不是 JSON 对象"]
    bad = [f"顶层字段 {k} 不在 Conversations 文档里" for k in body if k not in MISTRAL_TOP_KEYS]
    if not body.get("model") and not body.get("agent_id"):
        bad.append("model 和 agent_id 至少要有一个")
    if expect_model and body.get("model") != expect_model:
        bad.append(f"model 应为 {expect_model}：{body.get('model')!r}")
    if "stream" in body and not isinstance(body["stream"], bool):
        bad.append("stream 必须是布尔值")
    if "instructions" in body and body["instructions"] is not None and not isinstance(body["instructions"], str):
        bad.append("instructions 必须是字符串")
    inputs = body.get("inputs")
    if isinstance(inputs, str):
        if not inputs:
            bad.append("inputs 不能为空")
    elif isinstance(inputs, list) and inputs:
        calls = set()
        for i, entry in enumerate(inputs):
            kind = entry.get("type", "message.input") if isinstance(entry, dict) else None
            if kind in ("message.input", "message.output"):
                if entry.get("role") not in ("user", "assistant"):
                    bad.append(f"inputs[{i}].role 只能是 user 或 assistant，系统提示要放 instructions：{entry.get('role')!r}")
                if not isinstance(entry.get("content"), (str, list)) or not entry.get("content"):
                    bad.append(f"inputs[{i}].content 必须是非空字符串或内容块数组")
            elif kind == "function.call":
                if not (entry.get("tool_call_id") and entry.get("name") and "arguments" in entry):
                    bad.append(f"inputs[{i}] function.call 需要 tool_call_id、name、arguments")
                calls.add(entry.get("tool_call_id"))
            elif kind == "function.result":
                if entry.get("tool_call_id") not in calls:
                    bad.append(f"inputs[{i}] function.result 前面没有对应的 function.call：{entry.get('tool_call_id')}")
                if not isinstance(entry.get("result"), str):
                    bad.append(f"inputs[{i}] function.result.result 必须是字符串")
            else:
                bad.append(f"inputs[{i}] 的 type 不认识：{kind!r}")
    else:
        bad.append("inputs 必填，字符串或非空数组")
    args = body.get("completion_args")
    if args is not None:
        if not isinstance(args, dict):
            bad.append("completion_args 必须是对象")
        else:
            bad += [f"completion_args.{k} 不在文档里" for k in args if k not in MISTRAL_COMPLETION_KEYS]
    for tool in body.get("tools") or []:
        if tool.get("type") == "function":
            fn = tool.get("function")
            if not isinstance(fn, dict) or not fn.get("name") or not isinstance(fn.get("parameters"), dict):
                bad.append(f"function 工具需要 function.name 和 function.parameters：{str(tool)[:80]}")
        elif tool.get("type") not in ("web_search", "web_search_premium", "code_interpreter", "image_generation", "document_library", "connector"):
            bad.append(f"工具 type 不认识：{tool.get('type')!r}")
    return bad


def pick_tool(names):
    """从请求给的工具里挑一个只读的，避免模拟模型去改数据。"""
    for pattern in (r"^(list|get|read|search)", r"(list|get|read|search)"):
        for name in names:
            if re.search(pattern, name, re.I):
                return name
    return names[0] if names else None


# ---------- 处理请求 ----------
class _UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True
    upstream = None

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        """后端的 HTTPS 代理被指到这里：谁想出外网都会在这里留下记录，并被拒绝。"""
        self.upstream.proxy_attempts.append(self.path)
        self.send_response(502)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def _dispatch(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        record = Recorded(method, self.path, self.headers, raw)
        mock = self.upstream
        with mock.lock:
            mock.requests.append(record)
        path = urlsplit(self.path).path
        try:
            if path == "/oauth2/token":
                record.route = "token"
                return self._token(record)
            match = re.fullmatch(r"/model/([^/]+)/(converse|converse-stream|invoke|invoke-with-response-stream)", path)
            if match:
                return self._bedrock(record, unquote(match.group(1)), match.group(2))
            if path == "/v1/conversations":
                record.route = "mistral"
                return self._mistral(record)
            match = re.fullmatch(r"/v1/projects/p/locations/us-east5/publishers/anthropic/models/([^/:]+):(rawPredict|streamRawPredict)", path)
            if match:
                record.route = "vertex"
                record.operation = match.group(2)
                return self._vertex(record, unquote(match.group(1)), match.group(2) == "streamRawPredict")
            if path == "/v1/messages":
                record.route = "anthropic"
                return self._plain_anthropic(record)
            if path == "/v1/chat/completions":
                record.route = "openai"
                return self._openai(record)
            if path.rstrip("/").endswith("/models"):
                record.route = "models"
                return self._json(200, {"object": "list", "data": [{"id": "mock", "object": "model"}]})
            mock.violations.append(f"未知路径 {method} {self.path}")
            return self._json(404, {"message": f"no such route: {self.path}"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    # ----- 响应工具 -----
    def _json(self, status, body, headers=()):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if not isinstance(body, bytes) else body
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("x-amzn-RequestId", "mock-request-id")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _start_stream(self, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("x-amzn-RequestId", "mock-request-id")
        self.end_headers()
        self.wfile.flush()

    def _chunk(self, data):
        if data:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

    def _send_sharded(self, frames):
        """按 TCP 片段发送：前几帧拆碎到跨越前导和多字节字符，中间几帧粘在一起发。"""
        sizes = (1, 3, 7, 16, 29)
        for frame in frames[:4]:
            position = step = 0
            while position < len(frame):
                size = sizes[step % len(sizes)]
                self._chunk(frame[position:position + size])
                position += size
                step += 1
                time.sleep(0.001)
        rest = frames[4:]
        for start in range(0, len(rest), 2):
            self._chunk(b"".join(rest[start:start + 2]))
            time.sleep(0.002)

    def _finish_chunks(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _drop(self):
        """不发结束块，直接断开连接。"""
        self.wfile.flush()
        self.close_connection = True
        self.connection.close()

    def _reject(self, record, problems, fmt="aws"):
        self.upstream.violations.extend(f"{record.path}: {p}" for p in problems)
        message = "; ".join(problems)[:500]
        if fmt == "google":
            return self._json(400, {"error": {"code": 400, "message": message, "status": "INVALID_ARGUMENT"}})
        if fmt == "mistral":
            return self._json(422, {"object": "error", "message": message, "type": "invalid_request_error", "code": "3001"})
        return self._json(400, {"message": message}, [("x-amzn-ErrorType", "ValidationException")])

    def _check_no_key_material(self, record):
        """服务账号 JSON 或私钥不能出现在任何请求头里。"""
        problems = []
        for name, value in record.headers.items():
            if "PRIVATE KEY" in value or "service_account" in value or (name.lower() == "x-api-key" and record.route == "vertex"):
                problems.append(f"请求头 {name} 带了不该发的凭据")
        return problems

    # ----- HTTP 错误 -----
    def _http_error_status(self):
        fault = self.upstream.fault
        match = re.fullmatch(r"http_(\d+)(_echo)?", fault)
        return int(match.group(1)) if match else None

    def _echo_suffix(self):
        """有些上游会在错误信息里带上收到的凭据。echo_secret 打开时模拟这种情况。"""
        if not self.upstream.echo_secret:
            return ""
        return f" (credential was: {_bearer(self.headers)})"

    def _bedrock_http_error(self, status):
        names = {401: "UnauthorizedException", 403: "AccessDeniedException", 429: "ThrottlingException", 500: "InternalServerException", 503: "ServiceUnavailableException"}
        name = names.get(status, "InternalServerException")
        self._json(status, {"message": f"mock {name}{self._echo_suffix()}"}, [("x-amzn-ErrorType", name)])

    def _mistral_http_error(self, status):
        if status in (401, 403):
            return self._json(status, {"message": f"Unauthorized{self._echo_suffix()}", "request_id": "mock"})
        return self._json(status, {"object": "error", "message": f"mock upstream error{self._echo_suffix()}", "type": "api_error", "param": None, "code": str(status)})

    def _vertex_http_error(self, status):
        if status in (401, 403):
            names = {401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED"}
            return self._json(status, {"error": {"code": status, "message": f"mock{self._echo_suffix()}", "status": names[status]}})
        kinds = {429: "rate_limit_error", 500: "api_error", 503: "overloaded_error"}
        return self._json(status, {"type": "error", "error": {"type": kinds.get(status, "api_error"), "message": f"mock{self._echo_suffix()}"}})

    # ----- Google token 端点 -----
    def _token(self, record):
        mock = self.upstream
        mock.token_requests.append(record)
        problems = []
        if record.method != "POST":
            problems.append("token 请求必须是 POST")
        if not (record.headers.get("Content-Type") or "").startswith("application/x-www-form-urlencoded"):
            problems.append(f"Content-Type 必须是 application/x-www-form-urlencoded：{record.headers.get('Content-Type')}")
        form = parse_qs(record.raw.decode("utf-8", "replace"))
        if form.get("grant_type") != ["urn:ietf:params:oauth:grant-type:jwt-bearer"]:
            problems.append(f"grant_type 不对：{form.get('grant_type')}")
        assertion = (form.get("assertion") or [""])[0]
        mock.last_assertion = assertion
        problems += self.verify_assertion(assertion)
        if problems:
            mock.violations.extend(f"token: {p}" for p in problems)
            return self._json(400, {"error": "invalid_grant", "error_description": "; ".join(problems)[:300]})
        fault = mock.token_fault
        if fault == "invalid_grant":
            return self._json(400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."})
        if fault == "invalid_grant_echo":
            return self._json(400, {"error": "invalid_grant", "error_description": f"Invalid JWT: {assertion}"})
        if fault == "http_500":
            return self._json(500, {"error": "internal_failure", "error_description": "mock"})
        if fault == "not_json":
            return self._json(200, b"<html>not json</html>")
        if fault == "no_access_token":
            return self._json(200, {"token_type": "Bearer", "expires_in": 3600})
        if fault == "drop":
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b'{"access_tok')
            return self._drop()
        token = "ya29.mock-" + base64.urlsafe_b64encode(bytes(f"{time.time_ns()}", "ascii")).decode("ascii").rstrip("=")
        mock.issued_tokens.append(token)
        return self._json(200, {"access_token": token, "token_type": "Bearer", "expires_in": 3600, "scope": CLOUD_SCOPE})

    def verify_assertion(self, assertion):
        return verify_service_account_jwt(assertion, self.upstream.service_account, self.upstream.public_key, self.upstream.token_uri)

    # ----- Bedrock -----
    def _bedrock(self, record, model, operation):
        mock = self.upstream
        record.route = "bedrock_converse" if operation.startswith("converse") else "bedrock_invoke"
        record.operation = operation
        problems = self._check_no_key_material(record)
        if record.method != "POST":
            problems.append("必须是 POST")
        if mock.expect_model and model != mock.expect_model:
            problems.append(f"模型 ID 解码后应为 {mock.expect_model}：{model}")
        if not (record.headers.get("Content-Type") or "").startswith("application/json"):
            problems.append(f"Content-Type 必须是 application/json：{record.headers.get('Content-Type')}")
        if _bearer(record.headers) != mock.api_key:
            mock.violations.append(f"{record.path}: Authorization 必须是 Bearer <API Key>")
            return self._json(403, {"message": "Authorization header missing or wrong"}, [("x-amzn-ErrorType", "AccessDeniedException")])
        if record.json is None:
            problems.append("请求体不是合法 JSON")
        elif record.route == "bedrock_converse":
            problems += validate_converse(record.json)
        else:
            problems += validate_anthropic(record.json, "bedrock", operation == "invoke-with-response-stream")
        if problems:
            return self._reject(record, problems)
        status = self._http_error_status()
        if status:
            return self._bedrock_http_error(status)
        if record.route == "bedrock_converse":
            return self._converse_stream(record) if operation == "converse-stream" else self._converse_once(record)
        if operation == "invoke-with-response-stream":
            return self._invoke_stream(record)
        return self._anthropic_once(record)

    def _usage_converse(self):
        usage = {"inputTokens": USAGE["input"], "outputTokens": USAGE["output"], "totalTokens": USAGE["total"]}
        if self.upstream.cache_usage:
            usage.update(cacheReadInputTokens=CACHE_USAGE["read"], cacheWriteInputTokens=CACHE_USAGE["write"])
            usage["totalTokens"] += CACHE_USAGE["read"] + CACHE_USAGE["write"]
        return usage

    def _tool_stage(self, tool_names, has_result):
        """工具往返场景的阶段：first=该发工具调用；final=已收到结果；none=不是这个场景。"""
        mock = self.upstream
        if not mock.tool_round:
            return "none"
        if has_result:
            return "final"
        if not tool_names:
            mock.violations.append("工具往返场景里，请求没有带任何工具")
            return "none"
        mock.tool_used = pick_tool(tool_names)
        return "first"

    def _converse_tool_context(self, body):
        names = [t["toolSpec"]["name"] for t in (body.get("toolConfig") or {}).get("tools", []) if "toolSpec" in t]
        has_result = any("toolResult" in block for m in body["messages"] for block in m["content"])
        wants_thinking = isinstance((body.get("additionalModelRequestFields") or {}).get("thinking"), dict)
        return names, has_result, wants_thinking

    def _converse_once(self, record):
        mock = self.upstream
        if mock.fault == "malformed_json":
            return self._json(200, b'{"output": {"message": {"content": [{"text": "half')
        if mock.fault == "truncate":
            return self._truncated_body()
        if mock.fault == "empty_output":
            return self._json(200, {"stopReason": "end_turn", "usage": self._usage_converse(), "metrics": {"latencyMs": 1}})
        names, has_result, thinks = self._converse_tool_context(record.json)
        stage = self._tool_stage(names, has_result)
        if stage == "first":
            content = []
            if thinks:
                mock.tool_reasoning_sent = True
                content.append({"reasoningContent": {"reasoningText": {"text": THINKING, "signature": SIGNATURE}}})
            content.append({"toolUse": {"toolUseId": "tooluse_mock_1", "name": mock.tool_used, "input": {}}})
            return self._json(200, {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "tool_use", "usage": self._usage_converse(), "metrics": {"latencyMs": 1}})
        text = TOOL_FINAL_REPLY if stage == "final" else REPLY
        content = [{"text": text}]
        if stage == "none":
            content.insert(0, {"reasoningContent": {"reasoningText": {"text": THINKING, "signature": SIGNATURE}}})
        return self._json(200, {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "end_turn", "usage": self._usage_converse(), "metrics": {"latencyMs": 1}})

    def _truncated_body(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "5000")
        self.end_headers()
        self.wfile.write(b'{"output": {"message": {"content": [{"text": "half')
        self._drop()

    def _converse_stream(self, record):
        mock = self.upstream
        names, has_result, thinks = self._converse_tool_context(record.json)
        stage = self._tool_stage(names, has_result)
        frame = lambda name, payload, **kw: es.event_frame(name, {**payload, "p": "abcdefghij"}, **kw)
        frames = [frame("messageStart", {"role": "assistant"}, extra=es.all_header_types())]
        if stage == "first":
            index = 0
            if thinks:
                mock.tool_reasoning_sent = True
                frames.append(frame("contentBlockDelta", {"contentBlockIndex": 0, "delta": {"reasoningContent": {"text": THINKING}}}))
                frames.append(frame("contentBlockDelta", {"contentBlockIndex": 0, "delta": {"reasoningContent": {"signature": SIGNATURE}}}))
                frames.append(frame("contentBlockStop", {"contentBlockIndex": 0}))
                index = 1
            frames.append(frame("contentBlockStart", {"contentBlockIndex": index, "start": {"toolUse": {"toolUseId": "tooluse_mock_1", "name": mock.tool_used}}}))
            frames.append(frame("contentBlockDelta", {"contentBlockIndex": index, "delta": {"toolUse": {"input": "{"}}}))
            frames.append(frame("contentBlockDelta", {"contentBlockIndex": index, "delta": {"toolUse": {"input": "}"}}}))
            frames.append(frame("contentBlockStop", {"contentBlockIndex": index}))
            frames.append(frame("messageStop", {"stopReason": "tool_use"}))
            frames.append(frame("metadata", {"usage": self._usage_converse(), "metrics": {"latencyMs": 1}}))
            self._start_stream("application/vnd.amazon.eventstream")
            self._send_sharded(frames)
            return self._finish_chunks()
        index = 0
        if stage == "none":
            for piece in THINKING_CHUNKS:
                frames.append(frame("contentBlockDelta", {"contentBlockIndex": 0, "delta": {"reasoningContent": {"text": piece}}}))
            frames.append(frame("contentBlockDelta", {"contentBlockIndex": 0, "delta": {"reasoningContent": {"signature": SIGNATURE}}}))
            frames.append(frame("contentBlockStop", {"contentBlockIndex": 0}))
            index = 1
        if mock.forward_compat:
            frames.append(frame("someFutureEvent", {"note": "客户端要忽略不认识的事件"}))
        pieces = [TOOL_FINAL_REPLY] if stage == "final" else REPLY_CHUNKS
        text_frames = [frame("contentBlockDelta", {"contentBlockIndex": index, "delta": {"text": piece}}) for piece in pieces]
        tail = [frame("contentBlockStop", {"contentBlockIndex": index}), frame("messageStop", {"stopReason": "end_turn"}),
                frame("metadata", {"usage": self._usage_converse(), "metrics": {"latencyMs": 1}})]
        self._stream_with_fault(frames, text_frames, tail, lambda exc: es.exception_frame(exc, "mock stream exception"),
                                lambda corrupt: frame("contentBlockDelta", {"contentBlockIndex": index, "delta": {"text": "不应出现的文字"}}, corrupt=corrupt),
                                es.event_frame("contentBlockDelta", b'{"contentBlockIndex": 0, "delta": {"text": '))

    def _stream_with_fault(self, head, body, tail, exception, corrupt_frame, malformed):
        """按当前故障发 eventstream：先发一部分正文，再注入故障。"""
        fault = self.upstream.fault
        self._start_stream("application/vnd.amazon.eventstream")
        half = body[:2]
        if fault == "truncate":
            self._send_sharded(head + half)
            whole = body[2]
            self._chunk(whole[:len(whole) // 2])
            return self._drop()
        if fault == "truncate_prelude":
            self._send_sharded(head + half)
            self._chunk(body[2][:5])
            return self._drop()
        if fault == "no_terminal":
            self._send_sharded(head + half)
            return self._finish_chunks()
        if fault in ("bad_prelude_crc", "bad_message_crc"):
            self._send_sharded(head + half)
            self._chunk(corrupt_frame("prelude" if fault == "bad_prelude_crc" else "message"))
            self._chunk(body[2])
            return self._finish_chunks()
        if fault == "malformed_json":
            self._send_sharded(head + half)
            self._chunk(malformed)
            return self._finish_chunks()
        if fault == "exception_event":
            self._send_sharded(head + half + [exception("throttlingException")])
            return self._finish_chunks()
        if fault == "exception_internal":
            self._send_sharded(head + half + [exception("internalServerException")])
            return self._finish_chunks()
        if fault == "unmodeled_error":
            self._send_sharded(head + half + [es.unmodeled_error_frame("InternalFailure", "mock unmodeled error")])
            return self._finish_chunks()
        self._send_sharded(head + body + tail)
        self._finish_chunks()

    # ----- Bedrock 上的 Anthropic -----
    def _anthropic_tool_context(self, body):
        names = [t.get("name") for t in body.get("tools") or [] if t.get("name")]
        has_result = any(isinstance(b, dict) and b.get("type") == "tool_result"
                         for m in body["messages"] if isinstance(m.get("content"), list) for b in m["content"])
        thinking = body.get("thinking")
        wants_thinking = isinstance(thinking, dict) and thinking.get("type") in ("enabled", "adaptive")
        return names, has_result, wants_thinking

    def _anthropic_usage(self):
        usage = {"input_tokens": USAGE["input"], "output_tokens": 1}
        if self.upstream.cache_usage:
            usage.update(cache_read_input_tokens=CACHE_USAGE["read"], cache_creation_input_tokens=CACHE_USAGE["write"])
        return usage

    def _anthropic_events(self, body):
        """按 Anthropic 流式文档排好事件序列，分成开头、正文、结尾。"""
        mock = self.upstream
        names, has_result, thinks = self._anthropic_tool_context(body)
        stage = self._tool_stage(names, has_result)
        message = {"id": "msg_mock", "type": "message", "role": "assistant", "content": [], "model": "mock", "stop_reason": None, "stop_sequence": None, "usage": self._anthropic_usage()}
        head = [{"type": "message_start", "message": message}]
        reason = "end_turn"
        body_events = []
        index = 0
        if stage == "first":
            reason = "tool_use"
            if thinks:
                mock.tool_reasoning_sent = True
                head += [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
                         {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": THINKING}},
                         {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": SIGNATURE}},
                         {"type": "content_block_stop", "index": 0}]
                index = 1
            head += [{"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": "toolu_mock_1", "name": mock.tool_used, "input": {}}},
                     {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": ""}},
                     {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": "{}"}}]
        else:
            if stage == "none":
                head += [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}]
                head += [{"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": p}} for p in THINKING_CHUNKS]
                head += [{"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": SIGNATURE}},
                         {"type": "content_block_stop", "index": 0}]
                index = 1
            head.append({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            head.append({"type": "ping"})
            pieces = [TOOL_FINAL_REPLY] if stage == "final" else REPLY_CHUNKS
            body_events = [{"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": p}} for p in pieces]
        tail = [{"type": "content_block_stop", "index": index},
                {"type": "message_delta", "delta": {"stop_reason": reason, "stop_sequence": None}, "usage": {"output_tokens": USAGE["output"]}},
                {"type": "message_stop"}]
        return head, body_events, tail

    def _anthropic_once(self, record):
        mock = self.upstream
        if mock.fault == "malformed_json":
            return self._json(200, b'{"content": [{"type": "text", "text": "half')
        if mock.fault == "truncate":
            return self._truncated_body()
        if mock.fault == "empty_output":
            return self._json(200, {"id": "msg_mock", "type": "message", "role": "assistant", "stop_reason": "end_turn"})
        names, has_result, thinks = self._anthropic_tool_context(record.json)
        stage = self._tool_stage(names, has_result)
        usage = {**self._anthropic_usage(), "output_tokens": USAGE["output"]}
        if stage == "first":
            content = []
            if thinks:
                mock.tool_reasoning_sent = True
                content.append({"type": "thinking", "thinking": THINKING, "signature": SIGNATURE})
            content.append({"type": "tool_use", "id": "toolu_mock_1", "name": mock.tool_used, "input": {}})
            reason = "tool_use"
        else:
            content = [{"type": "text", "text": TOOL_FINAL_REPLY if stage == "final" else REPLY}]
            if stage == "none":
                content.insert(0, {"type": "thinking", "thinking": THINKING, "signature": SIGNATURE})
            reason = "end_turn"
        return self._json(200, {"id": "msg_mock", "type": "message", "role": "assistant", "model": "mock", "content": content, "stop_reason": reason, "stop_sequence": None, "usage": usage})

    def _invoke_stream(self, record):
        head, body, tail = self._anthropic_events(record.json)
        frame = es.chunk_frame
        if not body:
            self._start_stream("application/vnd.amazon.eventstream")
            self._send_sharded([frame(e) for e in head + tail])
            return self._finish_chunks()
        malformed = es.event_frame("chunk", {"bytes": base64.b64encode(b'{"type": "content_block_delta", "index": ').decode("ascii")})
        self._stream_with_fault([frame(e) for e in head], [frame(e) for e in body], [frame(e) for e in tail],
                                lambda exc: es.exception_frame(exc, "mock stream exception"),
                                lambda corrupt: frame(body[0], corrupt=corrupt), malformed)

    # ----- SSE 公共 -----
    def _send_sse_sharded(self, payloads):
        """SSE 也切碎发：多字节字符和换行符可能落在两个 TCP 片段里。"""
        for index, data in enumerate(payloads):
            if index < 4:
                for start in range(0, len(data), 11):
                    self._chunk(data[start:start + 11])
                    time.sleep(0.001)
            else:
                self._chunk(data)
                time.sleep(0.002)

    def _anthropic_sse(self, record):
        fault = self.upstream.fault
        head, body, tail = self._anthropic_events(record.json)
        encode = lambda e: f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode("utf-8")
        self._start_stream("text/event-stream")
        if not body:
            self._send_sse_sharded([encode(e) for e in head + tail])
            return self._finish_chunks()
        partial = [encode(e) for e in head + body[:2]]
        if fault == "truncate":
            self._send_sse_sharded(partial)
            whole = encode(body[2])
            self._chunk(whole[:len(whole) // 2])
            return self._drop()
        if fault == "no_terminal":
            self._send_sse_sharded(partial)
            return self._finish_chunks()
        if fault == "malformed_json":
            self._send_sse_sharded(partial + [b'event: content_block_delta\ndata: {"type": "content_block_delta", "index":\n\n'])
            return self._finish_chunks()
        if fault in ("exception_event", "exception_internal", "unmodeled_error"):
            error = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
            self._send_sse_sharded(partial + [encode(error)])
            return self._finish_chunks()
        extra = [encode({"type": "some_future_event"})] if self.upstream.forward_compat else []
        self._send_sse_sharded([encode(e) for e in head] + extra + [encode(e) for e in body + tail])
        self._finish_chunks()

    # ----- Vertex -----
    def _vertex(self, record, model, stream):
        mock = self.upstream
        problems = self._check_no_key_material(record)
        if record.method != "POST":
            problems.append("必须是 POST")
        if mock.expect_model and model != mock.expect_model:
            problems.append(f"模型应为 {mock.expect_model}：{model}")
        token = _bearer(record.headers)
        if token not in mock.issued_tokens:
            mock.violations.append(f"{record.path}: Authorization 必须是 Bearer <token 端点发的 access token>")
            return self._json(401, {"error": {"code": 401, "message": "Request had invalid authentication credentials.", "status": "UNAUTHENTICATED"}})
        if record.json is None:
            problems.append("请求体不是合法 JSON")
        else:
            problems += validate_anthropic(record.json, "vertex", stream)
        if problems:
            return self._reject(record, problems, "google")
        status = self._http_error_status()
        if status:
            return self._vertex_http_error(status)
        return self._anthropic_sse(record) if stream else self._anthropic_once(record)

    def _plain_anthropic(self, record):
        """现有的 anthropic_messages 协议，只做对照。"""
        mock = self.upstream
        if record.headers.get("x-api-key") != mock.api_key and _bearer(record.headers) != mock.api_key:
            return self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
        status = self._http_error_status()
        if status:
            return self._vertex_http_error(status)
        if record.json and record.json.get("stream"):
            return self._anthropic_sse(record)
        return self._anthropic_once(record)

    # ----- Mistral -----
    def _mistral(self, record):
        mock = self.upstream
        problems = self._check_no_key_material(record)
        if record.method != "POST":
            problems.append("必须是 POST")
        if not (record.headers.get("Content-Type") or "").startswith("application/json"):
            problems.append(f"Content-Type 必须是 application/json：{record.headers.get('Content-Type')}")
        if _bearer(record.headers) != mock.api_key:
            mock.violations.append(f"{record.path}: Authorization 必须是 Bearer <API Key>")
            return self._json(401, {"message": "Unauthorized", "request_id": "mock"})
        if record.json is None:
            problems.append("请求体不是合法 JSON")
        else:
            problems += validate_mistral(record.json, mock.expect_model)
        if problems:
            return self._reject(record, problems, "mistral")
        status = self._http_error_status()
        if status:
            return self._mistral_http_error(status)
        return self._mistral_stream(record) if record.json.get("stream") else self._mistral_once(record)

    def _mistral_usage(self):
        return {"prompt_tokens": USAGE["input"], "completion_tokens": USAGE["output"], "total_tokens": USAGE["total"]}

    def _mistral_tool_context(self, body):
        names = [(t.get("function") or {}).get("name") for t in body.get("tools") or [] if t.get("type") == "function"]
        inputs = body["inputs"] if isinstance(body["inputs"], list) else []
        has_result = any(isinstance(e, dict) and e.get("type") == "function.result" for e in inputs)
        return [n for n in names if n], has_result

    def _mistral_once(self, record):
        mock = self.upstream
        if mock.fault == "malformed_json":
            return self._json(200, b'{"conversation_id": "conv_mock", "outputs": [{"content": "half')
        if mock.fault == "truncate":
            return self._truncated_body()
        if mock.fault == "empty_output":
            return self._json(200, {"object": "conversation.response", "conversation_id": "conv_mock", "usage": self._mistral_usage()})
        names, has_result = self._mistral_tool_context(record.json)
        stage = self._tool_stage(names, has_result)
        base = {"object": "entry", "created_at": "2026-11-07T00:00:00Z", "completed_at": "2026-11-07T00:00:01Z", "id": "msg_mock"}
        if stage == "first":
            outputs = [{**base, "type": "function.call", "tool_call_id": "call_mock_1", "name": mock.tool_used, "arguments": "{}"}]
        elif stage == "final":
            outputs = [{**base, "type": "message.output", "role": "assistant", "model": "mock", "content": TOOL_FINAL_REPLY}]
        else:
            content = [{"type": "thinking", "thinking": [{"type": "text", "text": THINKING}], "closed": True}, {"type": "text", "text": REPLY}]
            outputs = [{**base, "type": "message.output", "role": "assistant", "model": "mock", "content": content}]
        return self._json(200, {"object": "conversation.response", "conversation_id": "conv_mock", "outputs": outputs, "usage": self._mistral_usage()})

    def _mistral_stream(self, record):
        mock = self.upstream
        fault = mock.fault
        names, has_result = self._mistral_tool_context(record.json)
        stage = self._tool_stage(names, has_result)

        def encode(event):
            return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")

        def delta(content, index):
            return {"type": "message.output.delta", "created_at": "2026-11-07T00:00:00Z", "output_index": 0, "id": "msg_mock", "content_index": index, "model": "mock", "role": "assistant", "content": content}

        started = {"type": "conversation.response.started", "created_at": "2026-11-07T00:00:00Z", "conversation_id": "conv_mock"}
        done = {"type": "conversation.response.done", "created_at": "2026-11-07T00:00:01Z", "usage": self._mistral_usage()}
        self._start_stream("text/event-stream")
        if stage == "first":
            base = {"type": "function.call.delta", "created_at": "2026-11-07T00:00:00Z", "output_index": 0, "id": "fc_mock", "name": mock.tool_used, "tool_call_id": "call_mock_1"}
            self._send_sse_sharded([encode(started), encode({**base, "arguments": "{"}), encode({**base, "arguments": "}"}), encode(done)])
            return self._finish_chunks()
        if stage == "final":
            self._send_sse_sharded([encode(started), encode(delta(TOOL_FINAL_REPLY, 0)), encode(done)])
            return self._finish_chunks()
        head = [encode(started)]
        for piece in THINKING_CHUNKS:
            head.append(encode(delta({"type": "thinking", "thinking": [{"type": "text", "text": piece}]}, 0)))
        body = [encode(delta(piece, 1)) for piece in REPLY_CHUNKS]
        partial = head + body[:2]
        if fault == "truncate":
            self._send_sse_sharded(partial)
            self._chunk(body[2][:len(body[2]) // 2])
            return self._drop()
        if fault == "no_terminal":
            self._send_sse_sharded(partial)
            return self._finish_chunks()
        if fault == "malformed_json":
            self._send_sse_sharded(partial + [b'event: message.output.delta\ndata: {"type": "message.output.delta", "content":\n\n'])
            return self._finish_chunks()
        if fault in ("exception_event", "exception_internal", "unmodeled_error"):
            error = {"type": "conversation.response.error", "created_at": "2026-11-07T00:00:01Z", "message": "mock stream error", "code": 3000}
            self._send_sse_sharded(partial + [encode(error)])
            return self._finish_chunks()
        extra = [encode({"type": "agent.handoff.started", "id": "h", "next_agent_id": "a", "next_agent_name": "b"})] if mock.forward_compat else []
        self._send_sse_sharded(head + extra + body + [encode(done)])
        self._finish_chunks()

    # ----- OpenAI 兼容（只做对照和核心错误路径） -----
    def _openai(self, record):
        mock = self.upstream
        if _bearer(record.headers) != mock.api_key:
            return self._json(401, {"error": {"message": "invalid api key", "type": "invalid_request_error"}})
        status = self._http_error_status()
        if status:
            return self._json(status, {"error": {"message": f"mock upstream error{self._echo_suffix()}", "type": "api_error"}})
        if mock.fault == "malformed_json" and not (record.json or {}).get("stream"):
            return self._json(200, b'{"choices": [{"message": {"content": "half')
        if mock.fault == "empty_output" and not (record.json or {}).get("stream"):
            return self._json(200, {"id": "mock", "object": "chat.completion", "model": "mock"})
        usage = {"prompt_tokens": USAGE["input"], "completion_tokens": USAGE["output"], "total_tokens": USAGE["total"]}
        if not (record.json or {}).get("stream"):
            return self._json(200, {"id": "mock", "object": "chat.completion", "model": "mock", "usage": usage,
                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY, "reasoning_content": THINKING}, "finish_reason": "stop"}]})
        self._start_stream("text/event-stream")

        def send(delta, finish=None, extra=None):
            chunk = {"id": "mock", "object": "chat.completion.chunk", "model": "mock", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **(extra or {})}
            self._chunk(b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n")

        send({"role": "assistant"})
        for piece in THINKING_CHUNKS:
            send({"reasoning_content": piece})
        for piece in REPLY_CHUNKS[:2]:
            send({"content": piece})
        if mock.fault == "truncate":
            return self._drop()
        for piece in REPLY_CHUNKS[2:]:
            send({"content": piece})
        send({}, "stop", {"usage": usage})
        self._chunk(b"data: [DONE]\n\n")
        self._finish_chunks()


def verify_service_account_jwt(assertion, service_account, public_key, token_uri):
    """依据 Google 服务账号文档校验签名和声明，返回问题列表。"""
    if not assertion:
        return ["缺少 assertion"]
    problems = []
    try:
        header = jwt.get_unverified_header(assertion)
    except jwt.PyJWTError as exc:
        return [f"assertion 不是合法 JWT：{exc}"]
    if header.get("alg") != "RS256":
        problems.append(f"JWT 头 alg 必须是 RS256：{header.get('alg')}")
    if header.get("typ") != "JWT":
        problems.append(f"JWT 头 typ 必须是 JWT：{header.get('typ')}")
    if "kid" in header and header["kid"] != service_account.get("private_key_id"):
        problems.append(f"JWT 头 kid 应为 private_key_id：{header['kid']}")
    try:
        claims = jwt.decode(assertion, public_key, algorithms=["RS256"], options={"verify_aud": False, "verify_exp": False, "verify_iat": False, "verify_nbf": False})
    except jwt.PyJWTError as exc:
        return problems + [f"JWT 签名校验失败：{exc}"]
    if claims.get("iss") != service_account["client_email"]:
        problems.append(f"iss 必须是服务账号邮箱：{claims.get('iss')}")
    scopes = str(claims.get("scope") or "").split(" ")
    if CLOUD_SCOPE not in scopes:
        problems.append(f"scope 必须包含 {CLOUD_SCOPE}：{claims.get('scope')}")
    if claims.get("aud") not in (token_uri, GOOGLE_TOKEN_AUD):
        problems.append(f"aud 应为 token 端点：{claims.get('aud')}")
    now = time.time()
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, (int, float)) or abs(iat - now) > 300:
        problems.append(f"iat 必须是当前时间的 Unix 秒：{iat}")
    if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)) or exp <= iat or exp - iat > 3600:
        problems.append(f"exp 必须晚于 iat 且不超过 1 小时：iat={iat} exp={exp}")
    return problems
