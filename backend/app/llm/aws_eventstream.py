"""application/vnd.amazon.eventstream 二进制帧解析（T-832）。

格式依据 https://smithy.io/2.0/aws/amazon-eventstream.html ：

    total_length(u32) headers_length(u32) prelude_crc(u32) headers payload message_crc(u32)

全部大端。``prelude_crc`` 覆盖前 8 字节；``message_crc`` 覆盖从消息开头到它自身之前的全部字节。
两个校验失败都必须终止流。ConverseStream 与 Anthropic-on-Bedrock 的 invoke-with-response-stream 共用。
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from app.errors import AppError

EVENTSTREAM_CONTENT_TYPE = "application/vnd.amazon.eventstream"

_PRELUDE_LENGTH = 12
_MESSAGE_CRC_LENGTH = 4
_MAX_HEADERS_LENGTH = 131_072
_MAX_PAYLOAD_LENGTH = 25_165_824


class EventStreamError(ValueError):
    """帧结构或校验和无效；流必须终止。"""


@dataclass(frozen=True)
class EventStreamFrame:
    headers: dict[str, Any] = field(default_factory=dict)
    payload: bytes = b""

    def header_text(self, name: str) -> str:
        value = self.headers.get(name)
        return value if isinstance(value, str) else ""

    @property
    def message_type(self) -> str:
        return self.header_text(":message-type")

    @property
    def event_type(self) -> str:
        return self.header_text(":event-type")

    @property
    def is_failure(self) -> bool:
        return self.message_type in {"exception", "error"}

    def json_payload(self) -> dict[str, Any]:
        """payload 按 JSON 对象解析；空 payload 视为空对象。"""
        if not self.payload:
            return {}
        try:
            data = json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EventStreamError(f"payload is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise EventStreamError(f"payload is {type(data).__name__}, expected object")
        return data


def _parse_headers(raw: bytes) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    pos = 0
    end = len(raw)

    def take(count: int) -> bytes:
        nonlocal pos
        if pos + count > end:
            raise EventStreamError("header section truncated")
        chunk = raw[pos : pos + count]
        pos += count
        return chunk

    while pos < end:
        name_length = take(1)[0]
        if name_length == 0:
            raise EventStreamError("header name is empty")
        try:
            name = take(name_length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EventStreamError("header name is not UTF-8") from exc
        value_type = take(1)[0]
        value: Any
        if value_type == 0:
            value = True
        elif value_type == 1:
            value = False
        elif value_type == 2:
            value = struct.unpack(">b", take(1))[0]
        elif value_type == 3:
            value = struct.unpack(">h", take(2))[0]
        elif value_type == 4:
            value = struct.unpack(">i", take(4))[0]
        elif value_type in {5, 8}:  # long / timestamp（毫秒）
            value = struct.unpack(">q", take(8))[0]
        elif value_type in {6, 7}:  # byte_array / string
            length = struct.unpack(">H", take(2))[0]
            data = take(length)
            if value_type == 7:
                try:
                    value = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise EventStreamError(f"header {name} is not UTF-8") from exc
            else:
                value = data
        elif value_type == 9:
            value = take(16).hex()
        else:
            raise EventStreamError(f"unknown header value type {value_type}")
        headers[name] = value
    return headers


class EventStreamDecoder:
    """增量解码：``feed`` 接受任意切分的字节块，返回已完整的帧。"""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def has_partial_frame(self) -> bool:
        return bool(self._buffer)

    def feed(self, chunk: bytes) -> list[EventStreamFrame]:
        self._buffer.extend(chunk)
        frames: list[EventStreamFrame] = []
        while True:
            frame = self._next_frame()
            if frame is None:
                return frames
            frames.append(frame)

    def _next_frame(self) -> EventStreamFrame | None:
        buffer = self._buffer
        if len(buffer) < _PRELUDE_LENGTH:
            return None
        total_length, headers_length, prelude_crc = struct.unpack(">III", bytes(buffer[:_PRELUDE_LENGTH]))
        if zlib.crc32(bytes(buffer[:8])) != prelude_crc:
            raise EventStreamError("prelude CRC mismatch")
        payload_length = total_length - headers_length - _PRELUDE_LENGTH - _MESSAGE_CRC_LENGTH
        if payload_length < 0:
            raise EventStreamError(f"invalid frame lengths total={total_length} headers={headers_length}")
        if headers_length > _MAX_HEADERS_LENGTH or payload_length > _MAX_PAYLOAD_LENGTH:
            raise EventStreamError(f"frame too large total={total_length} headers={headers_length}")
        if len(buffer) < total_length:
            return None
        message = bytes(buffer[:total_length])
        del buffer[:total_length]
        expected_crc = struct.unpack(">I", message[-_MESSAGE_CRC_LENGTH:])[0]
        if zlib.crc32(message[:-_MESSAGE_CRC_LENGTH]) != expected_crc:
            raise EventStreamError("message CRC mismatch")
        headers_end = _PRELUDE_LENGTH + headers_length
        return EventStreamFrame(
            headers=_parse_headers(message[_PRELUDE_LENGTH:headers_end]),
            payload=message[headers_end:-_MESSAGE_CRC_LENGTH],
        )


# 异常帧名（小写）→ (code, message, status_code, retryable, upstream_status)
_EXCEPTION_MAP: dict[str, tuple[str, str, int, bool, int | None]] = {
    "throttlingexception": ("provider_quota_exceeded", "上游服务额度不足或请求过于频繁", 429, True, 429),
    "servicequotaexceededexception": ("provider_quota_exceeded", "上游服务额度不足", 429, False, 400),
    "modelnotreadyexception": ("provider_quota_exceeded", "模型尚未就绪，请稍后重试", 429, True, 429),
    "modeltimeoutexception": ("upstream_timeout", "模型处理超时", 504, True, 408),
    "serviceunavailableexception": ("upstream_request_failed", "上游服务暂时不可用", 502, True, 503),
    "internalserverexception": ("upstream_request_failed", "上游服务内部错误", 502, True, 500),
    "modelstreamerrorexception": ("upstream_request_failed", "模型流式生成出错", 502, True, 424),
    "modelerrorexception": ("upstream_request_failed", "模型处理出错", 502, False, 424),
    "validationexception": ("provider_request_invalid", "上游拒绝了请求参数", 400, False, 400),
    "accessdeniedexception": ("provider_auth_failed", "上游服务鉴权失败", 403, False, 403),
    "resourcenotfoundexception": ("provider_request_invalid", "上游找不到指定的模型或资源", 400, False, 404),
}


def frame_failure_error(frame: EventStreamFrame, *, source: str, provider: str, protocol: str) -> AppError:
    """把 ``:message-type: exception|error`` 帧转成统一错误。"""
    if frame.message_type == "exception":
        name = frame.header_text(":exception-type")
        try:
            text = str(frame.json_payload().get("message") or "")
        except EventStreamError:
            text = ""
    else:
        name = frame.header_text(":error-code")
        text = frame.header_text(":error-message")
    code, message, status_code, retryable, upstream_status = _EXCEPTION_MAP.get(
        name.lower(), ("upstream_request_failed", "上游流返回了错误", 502, False, None)
    )
    return AppError(
        code=code,
        message=message,
        detail=f"{name or 'unknown'}: {text}" if text else (name or "unknown"),
        source=source,
        status_code=status_code,
        retryable=retryable,
        provider=provider,
        protocol=protocol,
        upstream_status=upstream_status,
        suggested_action="稍后重试；持续失败时检查模型权限、区域和额度",
    )


def _invalid_stream_error(detail: str, *, source: str, provider: str, protocol: str) -> AppError:
    return AppError(
        code="stream_event_invalid",
        message="上游 eventstream 帧无效",
        detail=detail,
        source=source,
        status_code=502,
        retryable=True,
        provider=provider,
        protocol=protocol,
        suggested_action="稍后重试；持续失败时检查 API 地址是否指向 Bedrock Runtime",
    )


def _incomplete_stream_error(detail: str, *, source: str, provider: str, protocol: str) -> AppError:
    return AppError(
        code="stream_incomplete",
        message="上游响应流提前中断",
        detail=detail,
        source=source,
        status_code=502,
        retryable=True,
        provider=provider,
        protocol=protocol,
        suggested_action="稍后重试，并检查网络或上游服务状态",
    )


async def aiter_event_frames(
    response: httpx.Response,
    *,
    source: str,
    provider: str,
    protocol: str,
) -> AsyncIterator[EventStreamFrame]:
    """读响应体并产出帧；异常帧、畸形帧、断流都抛 AppError。"""
    decoder = EventStreamDecoder()
    common = {"source": source, "provider": provider, "protocol": protocol}
    stream = response.aiter_bytes()
    while True:
        try:
            chunk = await stream.__anext__()
        except StopAsyncIteration:
            break
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as exc:
            raise _incomplete_stream_error(f"connection lost: {exc}", **common) from exc
        try:
            frames = decoder.feed(chunk)
        except EventStreamError as exc:
            raise _invalid_stream_error(str(exc), **common) from exc
        for frame in frames:
            if frame.is_failure:
                raise frame_failure_error(frame, **common)
            yield frame
    if decoder.has_partial_frame:
        raise _incomplete_stream_error("stream ended inside a frame", **common)


def frame_json(frame: EventStreamFrame, *, source: str, provider: str, protocol: str) -> dict[str, Any]:
    """帧 payload 转 JSON 对象；失败转统一错误。"""
    try:
        return frame.json_payload()
    except EventStreamError as exc:
        raise _invalid_stream_error(str(exc), source=source, provider=provider, protocol=protocol) from exc
