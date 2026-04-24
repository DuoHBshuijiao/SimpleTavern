"""
出站 HTTP 请求记录服务

功能：
- 记录后端 → 云端的出站 HTTP 请求（LLM /chat/completions、GitHub release 等）。
- 仅脱敏两类内容：API Key（headers + body 字段）、文件内容（替换为 headPreview + truncated 标记）。
- 图像（data:image/*;base64 或图像 URL）与 tool 相关字段原样保留。
- 按小时分片 JSONL 落盘到 data/http_log/YYYY-MM-DD-HH.jsonl。
- 只保留最近 30 分钟数据；清理由 http_log_sweeper 完成。

主要对外 API：
- log_outbound(source, method, url, ..., stream=False) 上下文管理器（同时支持 async with 与 async gen 场景）
- list_recent(since_minutes=30) -> list[dict]
- load_detail(record_id) -> dict | None
- clear_all()

文件关系：
- 被导入：openai_compat.py、update 路由、http_log 路由、http_log_sweeper
- 依赖：storage.get_repo_root 获取 data 目录
- 位置：服务层，纯存储与脱敏逻辑，不做业务判断
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Literal

logger = logging.getLogger(__name__)


# 保留窗口：与 sweeper 保持一致
RETENTION_MINUTES = 30
# 头 / body 中的敏感 key 名（大小写不敏感匹配）
_SENSITIVE_HEADER_KEYS = (
    "authorization",
    "x-api-key",
    "api-key",
    "openai-api-key",
    "anthropic-api-key",
    "x-goog-api-key",
    "proxy-authorization",
)
_SENSITIVE_BODY_KEYS = (
    "apikey",
    "api_key",
    "api-key",
    "token",
    "access_token",
    "accesstoken",
    "secret",
    "authorization",
)
# 文件相关字段（出现即视为文件内容，走 headPreview 截断）
_FILE_FIELD_KEYS = (
    "file_data",
    "fileData",
    "file_content",
    "fileContent",
    "b64_content",
    "base64_content",
)
# 文件内容截断后保留的字符数
_FILE_HEAD_PREVIEW_CHARS = 256
# 单条记录序列化后硬上限，防止单请求把磁盘打爆
_MAX_RECORD_BYTES = 8 * 1024 * 1024
# 字符串叶子节点硬上限（非图像、非 tool 字段）
_MAX_STRING_LEAF_CHARS = 1_000_000


def _redaction_marker() -> str:
    return "***"


def _data_root() -> Path:
    """延迟导入避免循环：复用 storage._data_dir 的约定。"""
    from app.storage import _data_dir  # type: ignore

    return _data_dir()


def get_http_log_dir() -> Path:
    d = _data_root() / "http_log"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


def redact_headers(headers: dict[str, Any] | Iterable[tuple[str, Any]] | None) -> dict[str, str]:
    """把敏感头替换为 ***，其它原样保留。"""
    if not headers:
        return {}
    items: list[tuple[str, Any]]
    if isinstance(headers, dict):
        items = list(headers.items())
    else:
        items = list(headers)
    out: dict[str, str] = {}
    for k, v in items:
        key = str(k)
        if key.lower() in _SENSITIVE_HEADER_KEYS:
            out[key] = _redaction_marker()
        else:
            out[key] = v if isinstance(v, str) else str(v)
    return out


def _looks_like_image_url_string(s: str) -> bool:
    if not isinstance(s, str):
        return False
    if s.startswith("data:image/"):
        return True
    low = s.lower()
    return (
        low.startswith("http://")
        or low.startswith("https://")
    ) and any(low.rsplit("?", 1)[0].endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))


def _estimate_image_bytes(url: str) -> int:
    """对 data-url 估算原始字节数；普通 URL 未知则返回 0。"""
    if not url.startswith("data:image/"):
        return 0
    idx = url.find(",")
    if idx < 0:
        return 0
    b64 = url[idx + 1 :]
    return max(0, (len(b64) * 3) // 4)


def _file_placeholder(raw: str, *, name: str | None = None, mime: str | None = None) -> dict[str, Any]:
    head = raw[:_FILE_HEAD_PREVIEW_CHARS]
    return {
        "_kind": "file",
        "name": name,
        "mime": mime,
        "bytes": len(raw.encode("utf-8", errors="ignore")) if isinstance(raw, str) else None,
        "headPreview": head,
        "truncated": True,
    }


def _redact_value(value: Any, *, key_hint: str | None = None, inside_tool: bool = False) -> Any:
    """
    递归脱敏：
    - 敏感字段（API key / token）直接替换为 ***
    - 文件字段替换为 headPreview 结构
    - 图像 data-url / URL 原样保留
    - tool / tool_calls / role=tool 的整体不截断（调用方已判断）
    - 超长字符串叶子（非图像、非 tool）截断到 _MAX_STRING_LEAF_CHARS
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if key_hint and key_hint.lower() in _FILE_FIELD_KEYS and len(value) > _FILE_HEAD_PREVIEW_CHARS:
            return _file_placeholder(value)
        # 图像 URL / data-url 原样
        if _looks_like_image_url_string(value):
            return value
        if inside_tool:
            return value
        if len(value) > _MAX_STRING_LEAF_CHARS:
            return value[:_MAX_STRING_LEAF_CHARS] + f"...[truncated {len(value) - _MAX_STRING_LEAF_CHARS} chars]"
        return value

    if isinstance(value, list):
        out_list: list[Any] = []
        for item in value:
            out_list.append(_redact_value(item, key_hint=key_hint, inside_tool=inside_tool))
        return out_list

    if isinstance(value, dict):
        out_dict: dict[str, Any] = {}
        # tool / tool_calls / role:tool 的 dict 里一律不截断字符串叶子
        tool_scope = inside_tool or _is_tool_scope(value, key_hint)
        for k, v in value.items():
            lk = str(k).lower()
            if lk in _SENSITIVE_BODY_KEYS and isinstance(v, str) and v:
                out_dict[k] = _redaction_marker()
                continue
            # openai 多模态 content 片段：type=image_url / type=input_image 原样
            if lk == "image_url" or lk == "input_image":
                out_dict[k] = v
                continue
            # openai 文件片段：{ type: "file", file: { file_data: "...", filename: "..." } }
            if lk == "file" and isinstance(v, dict):
                fname = v.get("filename") or v.get("name")
                raw_payload: str | None = None
                for fk in _FILE_FIELD_KEYS:
                    if isinstance(v.get(fk), str):
                        raw_payload = v[fk]
                        break
                if raw_payload is not None:
                    out_dict[k] = _file_placeholder(raw_payload, name=fname, mime=v.get("mime_type") or v.get("mime"))
                    continue
            if lk in _FILE_FIELD_KEYS and isinstance(v, str) and len(v) > _FILE_HEAD_PREVIEW_CHARS:
                out_dict[k] = _file_placeholder(v)
                continue
            out_dict[k] = _redact_value(v, key_hint=str(k), inside_tool=tool_scope)
        return out_dict

    return value


def _is_tool_scope(d: dict[str, Any], key_hint: str | None) -> bool:
    if key_hint and key_hint.lower() in ("tools", "tool_calls", "tool_call", "function_call"):
        return True
    role = d.get("role") if isinstance(d, dict) else None
    if role == "tool":
        return True
    return False


def redact_body(body: Any) -> Any:
    """对请求体 / 响应体进行脱敏拷贝。"""
    if body is None:
        return None
    try:
        cloned = copy.deepcopy(body)
    except Exception:
        cloned = body
    return _redact_value(cloned)


# ---------------------------------------------------------------------------
# 写盘
# ---------------------------------------------------------------------------


def _shard_path(ts_ms: int) -> Path:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
    return get_http_log_dir() / dt.strftime("%Y-%m-%d-%H.jsonl")


_write_lock = asyncio.Lock()


async def _write_record(record: dict[str, Any]) -> None:
    """把单条记录追加到当前小时分片。"""
    try:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        try:
            payload = json.dumps(
                {
                    **{k: v for k, v in record.items() if k in ("id", "ts", "source", "method", "url", "responseStatus")},
                    "_serializeError": True,
                },
                ensure_ascii=False,
            )
        except Exception:
            return
    if len(payload.encode("utf-8")) > _MAX_RECORD_BYTES:
        payload = json.dumps(
            {
                "id": record.get("id"),
                "ts": record.get("ts"),
                "source": record.get("source"),
                "method": record.get("method"),
                "url": record.get("url"),
                "responseStatus": record.get("responseStatus"),
                "durationMs": record.get("durationMs"),
                "error": record.get("error"),
                "streaming": record.get("streaming"),
                "_oversized": True,
                "_note": f"record exceeded {_MAX_RECORD_BYTES} bytes and was dropped",
            },
            ensure_ascii=False,
        )
    path = _shard_path(int(time.time() * 1000))
    async with _write_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(payload + "\n")
        except Exception:
            logger.exception("[http_log] failed to write record")


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------


def _iter_shards_from_newest() -> Iterable[Path]:
    d = get_http_log_dir()
    if not d.exists():
        return []
    items: list[tuple[str, Path]] = []
    for p in d.iterdir():
        if p.is_file() and p.name.endswith(".jsonl"):
            items.append((p.name, p))
    items.sort(reverse=True)
    return [p for _, p in items]


def _iter_shards_ascending() -> list[Path]:
    d = get_http_log_dir()
    if not d.exists():
        return []
    items: list[tuple[str, Path]] = []
    for p in d.iterdir():
        if p.is_file() and p.name.endswith(".jsonl"):
            items.append((p.name, p))
    items.sort()
    return [p for _, p in items]


def _record_meta(record: dict[str, Any]) -> dict[str, Any]:
    """列表接口的精简元数据（不含大 body）。"""
    return {
        "id": record.get("id"),
        "ts": record.get("ts"),
        "source": record.get("source"),
        "method": record.get("method"),
        "url": record.get("url"),
        "responseStatus": record.get("responseStatus"),
        "durationMs": record.get("durationMs"),
        "streaming": record.get("streaming"),
        "error": record.get("error"),
    }


def list_recent(since_minutes: int = RETENTION_MINUTES, limit: int = 500) -> list[dict[str, Any]]:
    """从旧到新返回最近 N 分钟的元数据列表。"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    rows: list[dict[str, Any]] = []
    for shard in _iter_shards_ascending():
        try:
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    ts_ms = int(rec.get("tsMs") or 0)
                    if ts_ms and ts_ms < cutoff_ms:
                        continue
                    rows.append(_record_meta(rec))
        except Exception:
            logger.exception("[http_log] failed to read shard %s", shard)
    rows.sort(key=lambda r: (r.get("ts") or ""))
    if len(rows) > limit:
        rows = rows[-limit:]
    return rows


def load_detail(record_id: str) -> dict[str, Any] | None:
    """查找一条完整记录。倒序扫分片以减少 IO。"""
    if not record_id:
        return None
    for shard in _iter_shards_from_newest():
        try:
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("id") == record_id:
                        return rec
        except Exception:
            logger.exception("[http_log] failed to scan shard %s", shard)
    return None


def clear_all() -> int:
    """手动清空所有分片，返回删除文件数。"""
    d = get_http_log_dir()
    if not d.exists():
        return 0
    count = 0
    for p in d.iterdir():
        if p.is_file() and p.name.endswith(".jsonl"):
            try:
                p.unlink()
                count += 1
            except Exception:
                logger.exception("[http_log] failed to unlink %s", p)
    return count


# ---------------------------------------------------------------------------
# 记录上下文
# ---------------------------------------------------------------------------


_Source = Literal["llm", "update", "other"]


@contextlib.asynccontextmanager
async def log_outbound(
    *,
    source: _Source,
    method: str,
    url: str,
    request_headers: dict[str, Any] | None = None,
    request_body: Any = None,
    streaming: bool = False,
    extra: dict[str, Any] | None = None,
) -> AsyncIterator["_RecordHandle"]:
    """
    包裹一次出站请求，无论成功/失败都在退出时落盘。

    用法：
        async with log_outbound(source="llm", method="POST", url=url,
                                 request_headers=headers, request_body=payload,
                                 streaming=True) as handle:
            # ... 发起 httpx 请求 ...
            handle.set_response(status=r.status_code, headers=r.headers, body=...)
            # 或 handle.append_stream_chunk("text") 多次追加后合并
            # 异常会被 handle.set_error 捕获
    """
    record_id = uuid.uuid4().hex
    started_at = time.time()
    handle = _RecordHandle(record_id=record_id)
    try:
        yield handle
    except BaseException as e:
        handle.set_error(repr(e))
        raise
    finally:
        duration_ms = int((time.time() - started_at) * 1000)
        ts_ms = int(time.time() * 1000)
        ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone().isoformat()
        record: dict[str, Any] = {
            "id": record_id,
            "ts": ts_iso,
            "tsMs": ts_ms,
            "durationMs": duration_ms,
            "source": source,
            "method": method.upper() if isinstance(method, str) else "GET",
            "url": _sanitize_url(url),
            "streaming": bool(streaming),
            "requestHeaders": redact_headers(request_headers),
            "requestBody": redact_body(request_body),
            "responseStatus": handle.response_status,
            "responseHeaders": redact_headers(handle.response_headers),
            "responseBody": _normalize_response_body(handle),
            "error": handle.error,
        }
        if extra:
            record["extra"] = extra
        await _write_record(record)


def _normalize_response_body(handle: "_RecordHandle") -> Any:
    """优先使用 structured body；其次 stream 聚合文本；否则 raw 文本。"""
    if handle.response_body is not None:
        return redact_body(handle.response_body)
    if handle.stream_chunks:
        joined = "".join(handle.stream_chunks)
        return redact_body(joined) if joined else None
    if handle.response_text is not None:
        return redact_body(handle.response_text)
    return None


def _sanitize_url(url: str) -> str:
    """URL 字符串中若含 apikey= 之类 query 参数，替换为 ***。"""
    if not isinstance(url, str) or "?" not in url:
        return url
    try:
        base, query = url.split("?", 1)
        pairs = query.split("&")
        out: list[str] = []
        for p in pairs:
            if "=" not in p:
                out.append(p)
                continue
            k, v = p.split("=", 1)
            if k.lower() in ("apikey", "api_key", "token", "access_token", "key"):
                out.append(f"{k}={_redaction_marker()}")
            else:
                out.append(f"{k}={v}")
        return base + "?" + "&".join(out)
    except Exception:
        return url


@contextlib.contextmanager
def log_outbound_sync(
    *,
    source: _Source,
    method: str,
    url: str,
    request_headers: dict[str, Any] | None = None,
    request_body: Any = None,
    streaming: bool = False,
    extra: dict[str, Any] | None = None,
):
    """同步版本的 log_outbound，用于 update 路由等非 async 调用方。"""
    record_id = uuid.uuid4().hex
    started_at = time.time()
    handle = _RecordHandle(record_id=record_id)
    err: BaseException | None = None
    try:
        yield handle
    except BaseException as e:
        handle.set_error(repr(e))
        err = e
        raise
    finally:
        try:
            duration_ms = int((time.time() - started_at) * 1000)
            ts_ms = int(time.time() * 1000)
            ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone().isoformat()
            record: dict[str, Any] = {
                "id": record_id,
                "ts": ts_iso,
                "tsMs": ts_ms,
                "durationMs": duration_ms,
                "source": source,
                "method": method.upper() if isinstance(method, str) else "GET",
                "url": _sanitize_url(url),
                "streaming": bool(streaming),
                "requestHeaders": redact_headers(request_headers),
                "requestBody": redact_body(request_body),
                "responseStatus": handle.response_status,
                "responseHeaders": redact_headers(handle.response_headers),
                "responseBody": _normalize_response_body(handle),
                "error": handle.error,
            }
            if extra:
                record["extra"] = extra
            _write_record_sync(record)
        except Exception:
            logger.exception("[http_log] sync finalizer failed")


def _write_record_sync(record: dict[str, Any]) -> None:
    try:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return
    if len(payload.encode("utf-8")) > _MAX_RECORD_BYTES:
        payload = json.dumps(
            {
                "id": record.get("id"),
                "ts": record.get("ts"),
                "source": record.get("source"),
                "method": record.get("method"),
                "url": record.get("url"),
                "responseStatus": record.get("responseStatus"),
                "_oversized": True,
            },
            ensure_ascii=False,
        )
    path = _shard_path(int(time.time() * 1000))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(payload + "\n")
    except Exception:
        logger.exception("[http_log] sync write failed")


class _RecordHandle:
    """log_outbound 暴露给调用方的把手：登记响应、错误、流块。"""

    __slots__ = (
        "record_id",
        "response_status",
        "response_headers",
        "response_body",
        "response_text",
        "stream_chunks",
        "error",
    )

    def __init__(self, *, record_id: str) -> None:
        self.record_id = record_id
        self.response_status: int | None = None
        self.response_headers: dict[str, Any] | None = None
        self.response_body: Any = None
        self.response_text: str | None = None
        self.stream_chunks: list[str] = []
        self.error: str | None = None

    def set_response(
        self,
        *,
        status: int | None = None,
        headers: dict[str, Any] | Iterable[tuple[str, Any]] | None = None,
        body: Any = None,
        text: str | None = None,
    ) -> None:
        if status is not None:
            self.response_status = int(status)
        if headers is not None:
            self.response_headers = dict(headers) if not isinstance(headers, dict) else headers
        if body is not None:
            self.response_body = body
        if text is not None:
            self.response_text = text

    def append_stream_text(self, text: str) -> None:
        if text:
            self.stream_chunks.append(text)

    def set_error(self, err: str | None) -> None:
        self.error = err
