"""检查的公共部分：注册检查、调用后端、解析 SSE、错误信封断言、密钥扫描。"""
import json
import re
import time
import traceback
from dataclasses import dataclass, field

import httpx

CHECKS = []
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class CheckFailed(Exception):
    pass


class Unspecified(Exception):
    """规格没有定义这个行为：记下观察结果，不算通过也不算失败。"""


@dataclass
class Check:
    name: str
    group: str
    doc: str
    fn: object


def check(name, doc=""):
    def register(fn):
        CHECKS.append(Check(name, name.split(".")[0], doc or (fn.__doc__ or "").strip(), fn))
        return fn

    return register


def add_check(name, doc, fn):
    CHECKS.append(Check(name, name.split(".")[0], doc, fn))


def ensure(condition, message):
    if not condition:
        raise CheckFailed(message)


def equal(actual, expected, label):
    if actual != expected:
        raise CheckFailed(f"{label}：期望 {expected!r}，实际 {actual!r}")


def unspecified(message):
    raise Unspecified(message)


def contains_text(node, text):
    """JSON 里某个字符串字段是否包含 text。不用序列化后的文本比较，转义会干扰。"""
    if isinstance(node, str):
        return text in node
    if isinstance(node, dict):
        return any(contains_text(value, text) for value in node.values())
    if isinstance(node, list):
        return any(contains_text(value, text) for value in node)
    return False


@dataclass
class GenResult:
    status: int = 0
    is_sse: bool = False
    events: list = field(default_factory=list)
    raw: bytes = b""
    json: object = None
    headers: dict = field(default_factory=dict)
    hung: bool = False
    transport_error: str = ""
    elapsed: float = 0.0

    def of(self, name):
        return [data for event, data in self.events if event == name]

    @property
    def meta(self):
        found = self.of("meta")
        return found[0] if found else None

    @property
    def text(self):
        return "".join(str(d.get("text", "")) for d in self.of("delta"))

    @property
    def reasoning(self):
        return "".join(str(d.get("text", "")) for d in self.of("reasoning"))

    @property
    def done(self):
        found = self.of("done")
        return found[-1] if found else None

    @property
    def error(self):
        found = self.of("error")
        if found:
            return found[-1]
        if isinstance(self.json, dict) and (self.status >= 400 or self.json.get("code")) and not self.json.get("ok"):
            return self.json
        return None

    @property
    def succeeded(self):
        if self.is_sse:
            return bool(self.done and self.done.get("ok"))
        return isinstance(self.json, dict) and self.json.get("ok") is True and self.status < 400

    def summary(self):
        if self.hung:
            return "请求悬挂，超时后被检查中止"
        if self.transport_error:
            return f"连接异常结束：{self.transport_error}"
        err = self.error
        if err:
            return f"HTTP {self.status}，错误 code={err.get('code')} message={str(err.get('message'))[:120]}"
        return f"HTTP {self.status}，{'SSE ' + ','.join(sorted(set(e for e, _ in self.events))) if self.is_sse else str(self.json)[:160]}"


def parse_sse(raw):
    events = []
    for block in re.split(rb"\r?\n\r?\n", raw):
        name = None
        lines = []
        for line in block.split(b"\n"):
            line = line.rstrip(b"\r")
            if line.startswith(b"event:"):
                name = line[6:].strip().decode("utf-8", "replace")
            elif line.startswith(b"data:"):
                lines.append(line[5:].lstrip(b" "))
        if not lines:
            continue
        text = b"\n".join(lines).decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError:
            data = {"_raw": text}
        events.append((name or "message", data))
    return events


class Api:
    def __init__(self, base_url):
        self.base = base_url
        self.client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(30.0), trust_env=False)

    def request(self, method, path, **kwargs):
        return self.client.request(method, path, **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def json_ok(self, method, path, **kwargs):
        response = self.request(method, path, **kwargs)
        ensure(response.status_code == 200, f"{method} {path} 应成功，实际 HTTP {response.status_code}：{response.text[:200]}")
        return response.json()

    def stream(self, path, body, deadline=60.0, headers=None):
        """发流式接口并读到结束。deadline 是墙钟上限，超过就算悬挂。"""
        result = GenResult()
        started = time.time()
        buffer = bytearray()
        timeout = httpx.Timeout(connect=5.0, read=deadline, write=10.0, pool=5.0)
        try:
            with self.client.stream("POST", path, json=body, timeout=timeout, headers=headers) as response:
                result.status = response.status_code
                result.headers = dict(response.headers)
                result.is_sse = "text/event-stream" in response.headers.get("content-type", "")
                for piece in response.iter_bytes():
                    buffer.extend(piece)
                    if time.time() - started > deadline:
                        result.hung = True
                        break
        except httpx.ReadTimeout:
            result.hung = True
        except httpx.HTTPError as exc:
            result.transport_error = f"{type(exc).__name__}: {exc}"
        result.elapsed = time.time() - started
        result.raw = bytes(buffer)
        if result.is_sse:
            result.events = parse_sse(result.raw)
        else:
            try:
                result.json = json.loads(result.raw) if result.raw else None
            except ValueError:
                result.json = None
        return result


# ---------- 错误信封 ----------
def assert_envelope(body, label="错误信封", status=None):
    """REST 错误信封：至少有 code、message、requestId（BACKEND-API.md 通用约定）。"""
    ensure(isinstance(body, dict), f"{label} 不是 JSON 对象：{str(body)[:200]}")
    for key in ("code", "message", "requestId"):
        ensure(isinstance(body.get(key), str) and body[key], f"{label} 缺少 {key}：{str(body)[:300]}")
    return body


def assert_rest_error(response, status, codes=None, label=""):
    """HTTP 状态、信封字段，以及响应头回传的请求标识。"""
    head = f"{label or response.request.method + ' ' + response.request.url.path}"
    ensure(response.status_code == status, f"{head} 应返回 HTTP {status}，实际 {response.status_code}：{response.text[:300]}")
    try:
        body = response.json()
    except ValueError as exc:
        raise CheckFailed(f"{head} 的错误体不是 JSON：{response.text[:200]}") from exc
    assert_envelope(body, head)
    if codes:
        ensure(body["code"] in codes, f"{head} 的 code 应为 {codes}，实际 {body['code']}")
    ensure(response.headers.get("x-request-id") == body["requestId"], f"{head} 响应头 X-Request-Id 与信封 requestId 不一致")
    return body


# ---------- 业务环境 ----------
class Env:
    """一次运行的共享环境。"""

    def __init__(self, api, mock, log_path=None, second_backend=None, restart_second=None, closed_port=None):
        self.api = api
        self.mock = mock
        self.log_path = log_path
        self.second_backend = second_backend
        self.restart_second = restart_second
        self.closed_port = closed_port
        self.character_id = None
        self.fixtures = {}

    def settings(self):
        return self.api.json_ok("GET", "/api/settings")

    def update_settings(self, **changes):
        settings = self.settings()
        settings.update(changes)
        return self.api.json_ok("PUT", "/api/settings", json=settings)

    def set_stream(self, enabled):
        saved = self.update_settings(streamEnabled=enabled)
        equal(saved.get("streamEnabled"), enabled, "streamEnabled 保存")

    def put_preset(self, preset):
        settings = self.settings()
        presets = [p for p in settings.get("apiPresets", []) if p.get("id") != preset["id"]]
        presets.append(preset)
        settings["apiPresets"] = presets
        saved = self.api.json_ok("PUT", "/api/settings", json=settings)
        match = [p for p in saved["apiPresets"] if p["id"] == preset["id"]]
        ensure(match, "预设没有保存")
        for key in ("protocol", "baseUrl", "authStyle", "providerParams"):
            if key in preset:
                equal(match[0].get(key), preset[key], f"预设字段 {key} 保存")
        return match[0]

    def ensure_character(self):
        if not self.character_id:
            # description 在界面上是“简介 · 不参与对话”，不发给模型；标记放在会进入系统提示的 personality
            body = {"name": "检查用角色", "description": "简介，不参与对话", "personality": "SYSMARKER-角色设定", "scenario": "长廊", "firstMessage": ""}
            self.character_id = self.api.json_ok("POST", "/api/characters", json=body)["id"]
        return self.character_id

    def new_chat(self, preset_id=None, model=None, reasoning=None, max_tokens=None, temperature=None):
        character = self.ensure_character()
        chat = self.api.json_ok("POST", "/api/chats", json={"characterId": character, "title": "检查会话"})
        if preset_id:
            params = {"model": model}
            # 不传 max_tokens 时走产品默认值
            if reasoning is not None:
                params["reasoningEffort"] = reasoning
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            if temperature is not None:
                params["temperature"] = temperature
            saved = self.api.json_ok("PUT", f"/api/chats/{chat['id']}", json={"overrides": {"presetId": preset_id, "params": params}})
            equal(saved["overrides"].get("presetId"), preset_id, "会话 presetId 保存")
            equal(saved["overrides"]["params"].get("model"), model, "会话模型保存")
        return chat["id"]

    def read_chat(self, chat_id):
        return self.api.json_ok("GET", f"/api/chats/{chat_id}")

    def generate(self, chat_id, message="你好，请继续。", deadline=60.0, headers=None, **extra):
        return self.api.stream("/api/generate/stream", {"chatId": chat_id, "userMessage": message, **extra}, deadline=deadline, headers=headers)

    def usage_summary(self, chat_id):
        return self.api.json_ok("GET", "/api/usage/summary", params={"scope": "chat", "chatId": chat_id})["summary"]


def run_checks(selected, env):
    """依次跑检查，返回 (通过, 失败, 规格未定义) 的列表。"""
    passed, failed, notes = [], [], []
    for item in selected:
        started = time.time()
        try:
            item.fn(env)
            passed.append(item)
            print(f"PASS {item.name}  ({time.time() - started:.1f}s)", flush=True)
        except Unspecified as exc:
            notes.append((item, str(exc)))
            print(f"NOTE {item.name}  规格未定义：{exc}", flush=True)
        except CheckFailed as exc:
            failed.append((item, str(exc)))
            print(f"FAIL {item.name}  {exc}", flush=True)
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            failed.append((item, f"检查异常 {detail}"))
            print(f"FAIL {item.name}  检查异常 {detail}", flush=True)
    return passed, failed, notes
