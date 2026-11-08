"""AWS eventstream 二进制帧的编码，依据 Smithy 的 amazon-eventstream 规范。

帧结构：总长度(u32) + 头部长度(u32) + 前导 CRC(u32) + 头部 + 载荷 + 消息 CRC(u32)，整数都是大端，CRC 是 CRC32。
解码器放在 checks_selftest.py，并且用另一种写法算 CRC，这样编码和解码不会一起错。
"""
import base64
import json
import struct
import uuid
import zlib

TRUE, FALSE, BYTE, SHORT, INT, LONG, BYTES, STRING, TIMESTAMP, UUID = range(10)


def encode_header(name, kind, value=None):
    raw = name.encode("utf-8")
    out = struct.pack(">B", len(raw)) + raw + struct.pack(">B", kind)
    if kind in (TRUE, FALSE):
        return out
    if kind == BYTE:
        return out + struct.pack(">b", value)
    if kind == SHORT:
        return out + struct.pack(">h", value)
    if kind == INT:
        return out + struct.pack(">i", value)
    if kind in (LONG, TIMESTAMP):
        return out + struct.pack(">q", value)
    if kind == BYTES:
        return out + struct.pack(">H", len(value)) + value
    if kind == STRING:
        data = value.encode("utf-8")
        return out + struct.pack(">H", len(data)) + data
    if kind == UUID:
        return out + value.bytes
    raise ValueError(f"未知的头部类型 {kind}")


def encode_frame(headers, payload=b"", corrupt=None):
    """headers 是 (名字, 类型, 值) 的列表。corrupt 取 prelude / message 时，故意写错对应的 CRC。"""
    head = b"".join(encode_header(*h) for h in headers)
    total = 16 + len(head) + len(payload)
    prelude = struct.pack(">II", total, len(head))
    prelude_crc = zlib.crc32(prelude)
    if corrupt == "prelude":
        prelude_crc ^= 0xFFFFFFFF
    body = prelude + struct.pack(">I", prelude_crc) + head + payload
    message_crc = zlib.crc32(body)
    if corrupt == "message":
        message_crc ^= 0xFFFFFFFF
    return body + struct.pack(">I", message_crc)


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") if not isinstance(payload, bytes) else payload


def event_frame(event_type, payload, extra=(), corrupt=None):
    """正常事件帧。payload 可以是 dict，也可以是原始字节（用来造畸形 JSON）。"""
    headers = [(":message-type", STRING, "event"), (":event-type", STRING, event_type),
               (":content-type", STRING, "application/json"), *extra]
    return encode_frame(headers, _json_bytes(payload), corrupt)


def exception_frame(exception_type, message):
    headers = [(":message-type", STRING, "exception"), (":exception-type", STRING, exception_type),
               (":content-type", STRING, "application/json")]
    return encode_frame(headers, _json_bytes({"message": message}))


def unmodeled_error_frame(code, message):
    headers = [(":message-type", STRING, "error"), (":error-code", STRING, code), (":error-message", STRING, message)]
    return encode_frame(headers)


def all_header_types():
    """每种头部类型各来一个，规范要求客户端都能解析。"""
    return [("x-true", TRUE, None), ("x-false", FALSE, None), ("x-byte", BYTE, -7), ("x-short", SHORT, 1234),
            ("x-int", INT, -123456), ("x-long", LONG, 1 << 40), ("x-blob", BYTES, b"\x00\xff\x10"),
            ("x-time", TIMESTAMP, 1_700_000_000_000), ("x-uuid", UUID, uuid.UUID(int=0x1234))]


def chunk_frame(anthropic_event, corrupt=None):
    """InvokeModelWithResponseStream 的 chunk 事件：bytes 字段是 base64 编码的模型事件。"""
    data = base64.b64encode(_json_bytes(anthropic_event)).decode("ascii")
    return event_frame("chunk", {"bytes": data, "p": "abcdefgh"}, corrupt=corrupt)
