"""自检：不启动后端，证明编码和模拟服务本身是对的，并且故障注入确实是坏的。

这里的解码器和 CRC 是另写的，不用 zlib，也不用 eventstream.py 的函数。
"""
import base64
import json
import struct
import time
import uuid

import httpx
import jwt

import eventstream as es
import fixtures
from harness import add_check, check, ensure, equal
from mock_upstream import CACHE_USAGE, CLOUD_SCOPE, REPLY, THINKING, USAGE, MockUpstream, verify_service_account_jwt

# AWS 文档《Setting up a streaming transcription》里的响应帧样例，用来核对 CRC 算法和帧结构。
AWS_DOC_FRAME = "AAAAUwAAAEP1RHpYBTpkYXRlCAAAAWiXUkMLEDpjaHVuay1zaWduYXR1cmUGACCt6Zy+uymwEK2SrLp/zVBI5eGn83jdBwCaRUBJA+eaDafqjqI="
MODEL = "anthropic.claude-sonnet-4-5-20250929-v1:0"
VERTEX_BASE = "/v1/projects/p/locations/us-east5/publishers/anthropic/models/claude-x"


def bitwise_crc32(data):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


class FrameError(Exception):
    pass


def decode_stream(data):
    """逐帧解码，长度不够或 CRC 不对都报错。"""
    frames = []
    position = 0
    while position < len(data):
        if len(data) - position < 16:
            raise FrameError("帧不完整：不够前导")
        total, head_length, prelude_crc = struct.unpack_from(">III", data, position)
        if bitwise_crc32(data[position:position + 8]) != prelude_crc:
            raise FrameError("前导 CRC 不对")
        if len(data) - position < total:
            raise FrameError("帧不完整：不够总长度")
        frame = data[position:position + total]
        if bitwise_crc32(frame[:-4]) != struct.unpack(">I", frame[-4:])[0]:
            raise FrameError("消息 CRC 不对")
        headers = {}
        offset = 12
        end = 12 + head_length
        while offset < end:
            size = frame[offset]
            name = frame[offset + 1:offset + 1 + size].decode("utf-8")
            offset += 1 + size
            kind = frame[offset]
            offset += 1
            if kind in (0, 1):
                value = kind == 0
            elif kind == 2:
                value = struct.unpack_from(">b", frame, offset)[0]
                offset += 1
            elif kind == 3:
                value = struct.unpack_from(">h", frame, offset)[0]
                offset += 2
            elif kind == 4:
                value = struct.unpack_from(">i", frame, offset)[0]
                offset += 4
            elif kind in (5, 8):
                value = struct.unpack_from(">q", frame, offset)[0]
                offset += 8
            elif kind in (6, 7):
                length = struct.unpack_from(">H", frame, offset)[0]
                offset += 2
                value = frame[offset:offset + length]
                offset += length
                if kind == 7:
                    value = value.decode("utf-8")
            elif kind == 9:
                value = uuid.UUID(bytes=frame[offset:offset + 16])
                offset += 16
            else:
                raise FrameError(f"未知头部类型 {kind}")
            headers[name] = value
        frames.append((headers, frame[end:-4]))
        position += total
    return frames


STATE = {"port": 9718}


def _mock():
    if "mock" not in STATE:
        key = fixtures.generate_rsa_private_key()
        mock = MockUpstream(STATE["port"]).start()
        info = fixtures.service_account_info(fixtures.private_key_pem(key), mock.token_uri)
        mock.service_account = info
        mock.public_key = fixtures.public_key_pem(key)
        STATE.update(mock=mock, key=key, info=info, other=fixtures.generate_rsa_private_key())
    return STATE


def stop_selftest_mock():
    if "mock" in STATE:
        STATE.pop("mock").stop()


def _setup(fault="ok", **kw):
    cache = _mock()
    mock = cache["mock"]
    mock.reset(fault=fault, **kw)
    mock.api_key = "selftest-key"
    mock.expect_model = None
    return mock


def _post(mock, path, body, key="selftest-key", headers=None):
    all_headers = {"Authorization": f"Bearer {key}", **(headers or {})} if key else dict(headers or {})
    return httpx.post(mock.url + path, json=body, headers=all_headers, timeout=10, trust_env=False)


def _stream_bytes(mock, path, body, key="selftest-key"):
    """读流式响应。连接被掐断时返回 (已读字节, True)。"""
    data = bytearray()
    try:
        with httpx.stream("POST", mock.url + path, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=10, trust_env=False) as response:
            ensure(response.status_code == 200, f"应为 200，实际 {response.status_code}")
            for piece in response.iter_raw():
                data.extend(piece)
    except httpx.HTTPError:
        return bytes(data), True
    return bytes(data), False


CONVERSE_BODY = {"messages": [{"role": "user", "content": [{"text": "hi"}]}], "system": [{"text": "s"}], "inferenceConfig": {"maxTokens": 10, "temperature": 0.4}}
INVOKE_BODY = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
VERTEX_BODY = {"anthropic_version": "vertex-2023-10-16", "max_tokens": 10, "stream": True, "messages": [{"role": "user", "content": "hi"}]}
MISTRAL_BODY = {"model": "m", "inputs": [{"role": "user", "content": "hi"}], "stream": True}


@check("selftest.eventstream.aws_doc_frame", "AWS 文档样例帧能被自检解码器解开，两个 CRC 都对上")
def _(_env):
    frames = decode_stream(base64.b64decode(AWS_DOC_FRAME))
    equal(len(frames), 1, "帧数")
    headers = frames[0][0]
    ensure(":date" in headers and ":chunk-signature" in headers, f"头部不对：{list(headers)}")
    equal(len(headers[":chunk-signature"]), 32, "签名长度")


@check("selftest.eventstream.round_trip", "编码出的帧被独立解码器解开，十种头部类型和载荷都一致")
def _(_env):
    payload = "中文载荷🙂".encode("utf-8")
    frame = es.event_frame("contentBlockDelta", payload, extra=es.all_header_types())
    headers, body = decode_stream(frame)[0]
    equal(body, payload, "载荷")
    equal(headers[":event-type"], "contentBlockDelta", ":event-type")
    equal(headers["x-true"], True, "布尔真")
    equal(headers["x-false"], False, "布尔假")
    equal(headers["x-byte"], -7, "byte")
    equal(headers["x-short"], 1234, "short")
    equal(headers["x-int"], -123456, "int")
    equal(headers["x-long"], 1 << 40, "long")
    equal(headers["x-blob"], b"\x00\xff\x10", "blob")
    equal(headers["x-time"], 1_700_000_000_000, "timestamp")
    equal(headers["x-uuid"], uuid.UUID(int=0x1234), "uuid")


@check("selftest.eventstream.corrupt", "故意写错的前导 CRC 和消息 CRC 会被解码器发现")
def _(_env):
    for corrupt in ("prelude", "message"):
        try:
            decode_stream(es.event_frame("x", {"a": 1}, corrupt=corrupt))
        except FrameError:
            continue
        raise AssertionError(f"{corrupt} CRC 错误没有被发现")


def _converse_frames(data):
    text, reasoning, usage, stop, order = "", "", None, None, []
    for headers, payload in decode_stream(data):
        order.append(headers.get(":event-type") or headers.get(":exception-type"))
        if headers.get(":message-type") == "exception":
            continue
        body = json.loads(payload)
        delta = body.get("delta") or {}
        text += delta.get("text", "")
        reasoning += (delta.get("reasoningContent") or {}).get("text", "")
        stop = body.get("stopReason", stop)
        usage = body.get("usage", usage)
    return text, reasoning, usage, stop, order


@check("selftest.mock.converse_stream_ok", "参考客户端读 converse-stream：文字、思考、用量和事件顺序符合文档")
def _(_env):
    mock = _setup()
    data, dropped = _stream_bytes(mock, f"/model/{MODEL}/converse-stream", CONVERSE_BODY)
    ensure(not dropped, "正常流不该断")
    text, reasoning, usage, stop, order = _converse_frames(data)
    equal(text, REPLY, "文字")
    equal(reasoning, THINKING, "思考")
    equal(usage["inputTokens"], USAGE["input"], "输入用量")
    equal(stop, "end_turn", "stopReason")
    equal(order[0], "messageStart", "第一帧")
    equal(order[-2:], ["messageStop", "metadata"], "最后两帧")
    equal(mock.violations, [], "违规")


@check("selftest.mock.stream_is_sharded", "流确实分很多次发出，帧跨越了 TCP 片段")
def _(_env):
    mock = _setup()
    pieces = []
    with httpx.stream("POST", f"{mock.url}/model/{MODEL}/converse-stream", json=CONVERSE_BODY, headers={"Authorization": "Bearer selftest-key"}, timeout=10, trust_env=False) as response:
        for piece in response.iter_raw():
            pieces.append(piece)
    frames = decode_stream(b"".join(pieces))
    ensure(len(pieces) > len(frames), f"读取次数 {len(pieces)} 应多于帧数 {len(frames)}")
    first_frame_length = struct.unpack(">I", pieces[0][:4])[0] if len(pieces[0]) >= 4 else 10 ** 9
    ensure(len(pieces[0]) < first_frame_length, "第一次读取不应包含完整的第一帧")


def _fault_frames(fault):
    def run(_env):
        mock = _setup(fault=fault)
        data, dropped = _stream_bytes(mock, f"/model/{MODEL}/converse-stream", CONVERSE_BODY)
        if fault in ("truncate", "truncate_prelude"):
            ensure(dropped, "应当断开连接")
            try:
                decode_stream(data)
            except FrameError:
                return
            raise AssertionError("截断的流应当解不完整")
        if fault in ("bad_prelude_crc", "bad_message_crc"):
            try:
                decode_stream(data)
            except FrameError as exc:
                ensure("CRC" in str(exc), f"应是 CRC 错误：{exc}")
                return
            raise AssertionError("CRC 错误的流应当解不开")
        frames = decode_stream(data)
        last_headers, last_payload = frames[-1]
        if fault == "no_terminal":
            ensure("messageStop" not in [h.get(":event-type") for h, _ in frames], "不该有 messageStop")
        elif fault == "malformed_json":
            try:
                json.loads(last_payload)
            except ValueError:
                return
            raise AssertionError("最后一帧应是畸形 JSON")
        elif fault == "exception_event":
            equal(last_headers[":message-type"], "exception", ":message-type")
            equal(last_headers[":exception-type"], "throttlingException", ":exception-type")
        elif fault == "unmodeled_error":
            equal(last_headers[":message-type"], "error", ":message-type")
            ensure(last_headers.get(":error-code"), "缺少 :error-code")
    return run


for _fault in ("truncate", "truncate_prelude", "no_terminal", "bad_prelude_crc", "bad_message_crc", "malformed_json", "exception_event", "unmodeled_error"):
    add_check(f"selftest.mock.fault.{_fault}", f"故障 {_fault} 发出的字节确实是坏的", _fault_frames(_fault))


@check("selftest.mock.invoke_stream_ok", "invoke-with-response-stream 的 chunk 帧解开后是 Anthropic 事件")
def _(_env):
    mock = _setup()
    data, _dropped = _stream_bytes(mock, f"/model/{MODEL}/invoke-with-response-stream", INVOKE_BODY)
    events = [json.loads(base64.b64decode(json.loads(payload)["bytes"])) for _h, payload in decode_stream(data)]
    text = "".join(e["delta"].get("text", "") for e in events if e["type"] == "content_block_delta")
    equal(text, REPLY, "文字")
    equal(events[0]["type"], "message_start", "第一个事件")
    equal(events[-1]["type"], "message_stop", "最后一个事件")
    equal(mock.violations, [], "违规")


@check("selftest.mock.mistral_stream_ok", "Mistral 流式事件能解出文字和用量")
def _(_env):
    mock = _setup()
    data, _dropped = _stream_bytes(mock, "/v1/conversations", MISTRAL_BODY)
    events = [json.loads(line[6:]) for line in data.decode("utf-8").splitlines() if line.startswith("data: ")]
    text = "".join(e["content"] for e in events if e["type"] == "message.output.delta" and isinstance(e["content"], str))
    equal(text, REPLY, "文字")
    equal(events[0]["type"], "conversation.response.started", "第一个事件")
    equal(events[-1]["usage"]["prompt_tokens"], USAGE["input"], "用量")
    equal(mock.violations, [], "违规")


def _make_jwt(key, info, **overrides):
    now = int(time.time())
    claims = {"iss": info["client_email"], "scope": CLOUD_SCOPE, "aud": info["token_uri"], "iat": now, "exp": now + 3600, **overrides}
    return jwt.encode(claims, fixtures.private_key_pem(key), algorithm="RS256", headers={"kid": info["private_key_id"]})


@check("selftest.mock.vertex_flow", "用合法 JWT 换 token，再带 token 调 streamRawPredict 成功")
def _(_env):
    mock = _setup()
    cache = _mock()
    assertion = _make_jwt(cache["key"], cache["info"])
    response = httpx.post(mock.token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, trust_env=False)
    equal(response.status_code, 200, "token 状态")
    token = response.json()["access_token"]
    data, _dropped = _stream_bytes(mock, f"{VERTEX_BASE}:streamRawPredict", VERTEX_BODY, key=token)
    ensure("第一段".encode("utf-8") in data, "SSE 里应有正文")
    equal(mock.violations, [], "违规")


def _jwt_rejected(mutate, expected):
    def run(_env):
        mock = _setup()
        cache = _mock()
        assertion = mutate(cache)
        response = httpx.post(mock.token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, trust_env=False)
        equal(response.status_code, 400, "应拒绝")
        ensure(any(expected in v for v in mock.violations), f"违规记录应提到 {expected}：{mock.violations}")
    return run


add_check("selftest.mock.jwt_forged", "别的私钥签的 JWT 被拒绝", _jwt_rejected(lambda c: _make_jwt(c["other"], c["info"]), "签名"))
add_check("selftest.mock.jwt_wrong_iss", "iss 不对的 JWT 被拒绝", _jwt_rejected(lambda c: _make_jwt(c["key"], c["info"], iss="x@y"), "iss"))
add_check("selftest.mock.jwt_long_exp", "有效期超过 1 小时的 JWT 被拒绝", _jwt_rejected(lambda c: _make_jwt(c["key"], c["info"], exp=int(time.time()) + 7200), "exp"))
add_check("selftest.mock.jwt_no_scope", "scope 不对的 JWT 被拒绝", _jwt_rejected(lambda c: _make_jwt(c["key"], c["info"], scope="other"), "scope"))
add_check("selftest.mock.jwt_wrong_aud", "aud 不对的 JWT 被拒绝", _jwt_rejected(lambda c: _make_jwt(c["key"], c["info"], aud="https://x.test"), "aud"))


@check("selftest.mock.vertex_needs_token", "没有 token 端点发的 token 时 Vertex 路由返回 401")
def _(_env):
    mock = _setup()
    response = _post(mock, f"{VERTEX_BASE}:rawPredict", VERTEX_BODY, key="not-issued")
    equal(response.status_code, 401, "状态")
    ensure(mock.violations, "应记录违规")


def _rejected(path, body, expected, key="selftest-key", headers=None):
    def run(_env):
        mock = _setup()
        response = _post(mock, path, body, key=key, headers=headers)
        ensure(response.status_code >= 400, f"应拒绝，实际 {response.status_code}")
        ensure(any(expected in v for v in mock.violations), f"违规记录应提到 {expected}：{mock.violations}")
    return run


_cases = [
    ("no_auth", f"/model/{MODEL}/converse", CONVERSE_BODY, "Authorization", None),
    ("wrong_key", f"/model/{MODEL}/converse", CONVERSE_BODY, "Authorization", "wrong"),
    ("unknown_path", "/model/x/y/converse", CONVERSE_BODY, "未知路径", "selftest-key"),
    ("converse_stream_field", f"/model/{MODEL}/converse", {**CONVERSE_BODY, "stream": True}, "stream", "selftest-key"),
    ("converse_top_max_tokens", f"/model/{MODEL}/converse", {**CONVERSE_BODY, "max_tokens": 5}, "max_tokens", "selftest-key"),
    ("converse_string_content", f"/model/{MODEL}/converse", {"messages": [{"role": "user", "content": "hi"}]}, "content", "selftest-key"),
    ("converse_two_keys_block", f"/model/{MODEL}/converse", {"messages": [{"role": "user", "content": [{"text": "a", "image": {}}]}]}, "联合", "selftest-key"),
    ("converse_system_role", f"/model/{MODEL}/converse", {"messages": [{"role": "system", "content": [{"text": "a"}]}]}, "role", "selftest-key"),
    ("converse_empty_system", f"/model/{MODEL}/converse", {**CONVERSE_BODY, "system": [{"text": ""}]}, "system", "selftest-key"),
    ("invoke_model_in_body", f"/model/{MODEL}/invoke", {**INVOKE_BODY, "model": "x"}, "model", "selftest-key"),
    ("invoke_stream_in_body", f"/model/{MODEL}/invoke-with-response-stream", {**INVOKE_BODY, "stream": True}, "stream", "selftest-key"),
    ("invoke_wrong_version", f"/model/{MODEL}/invoke", {**INVOKE_BODY, "anthropic_version": "2023-06-01"}, "anthropic_version", "selftest-key"),
    ("mistral_messages_field", "/v1/conversations", {"model": "m", "messages": []}, "messages", "selftest-key"),
    ("mistral_system_role", "/v1/conversations", {"model": "m", "inputs": [{"role": "system", "content": "s"}]}, "instructions", "selftest-key"),
    ("mistral_no_model", "/v1/conversations", {"inputs": "hi"}, "agent_id", "selftest-key"),
    ("mistral_top_temperature", "/v1/conversations", {"model": "m", "inputs": "hi", "temperature": 0.5}, "temperature", "selftest-key"),
]
for _name, _path, _body, _expected, _key in _cases:
    add_check(f"selftest.mock.reject.{_name}", f"模拟上游拒绝不符合文档的请求：{_name}", _rejected(_path, _body, _expected, key=_key))


@check("selftest.mock.cache_usage", "打开缓存用量后，converse 响应带文档里的缓存字段")
def _(_env):
    mock = _setup(cache_usage=True)
    response = _post(mock, f"/model/{MODEL}/converse", CONVERSE_BODY)
    usage = response.json()["usage"]
    equal(usage["cacheReadInputTokens"], CACHE_USAGE["read"], "缓存读")
    equal(usage["cacheWriteInputTokens"], CACHE_USAGE["write"], "缓存写")
