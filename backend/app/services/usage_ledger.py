"""消息 generation metadata 与 append-only usage ledger（T-807）。

路径：
- ``data/usage/YYYY-MM.jsonl``：按月分片，一行一个事件
- ``data/usage/usage_index.json``：计数与最近 eventId
- ``data/usage/repair.jsonl``：账本写入失败时的可修复队列

不实现定价引擎（T-808）。供应商未返回 cost 时标记 unknown，不得填 0。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.errors import AppError
from app.storage import append_jsonl_object, get_usage_dir, read_json, write_json


logger = logging.getLogger(__name__)

LEDGER_VERSION = 1
METADATA_VERSION = 1
_INDEX_NAME = "usage_index.json"
_REPAIR_NAME = "repair.jsonl"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _month_shard(ts: datetime | None = None) -> str:
    dt = ts or datetime.now().astimezone()
    return dt.strftime("%Y-%m.jsonl")


def _index_path():
    return get_usage_dir() / _INDEX_NAME


def _repair_path():
    return get_usage_dir() / _REPAIR_NAME


def _shard_path(ts: datetime | None = None):
    return get_usage_dir() / _month_shard(ts)


def usage_tokens_view(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """把消息/SSE 上的归一化 usage 收成 metadata.usage；缺字段不填 0。"""
    if not isinstance(usage, dict) or not usage:
        return None
    aliases = (
        ("inputTokens", "input_tokens"),
        ("outputTokens", "output_tokens"),
        ("totalTokens", "total_tokens"),
        ("cacheReadInputTokens", "cache_read_input_tokens"),
        ("cacheWriteInputTokens", "cache_write_input_tokens"),
        ("reasoningTokens", "reasoning_tokens"),
    )
    out: dict[str, Any] = {}
    for camel, snake in aliases:
        val = usage.get(camel)
        if val is None:
            val = usage.get(snake)
        if val is not None:
            out[camel] = val
    tier = usage.get("serviceTier") or usage.get("service_tier")
    if tier:
        out["serviceTier"] = tier
    if usage.get("fastRequested") is True:
        out["fastRequested"] = True
    return out or None


def cost_from_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """仅保留供应商返回的 cost；没有就不写，禁止用 0 冒充精确值。"""
    if not isinstance(usage, dict):
        return None
    raw = usage.get("cost")
    amount = None
    currency = None
    if isinstance(raw, dict):
        amount = raw.get("amount")
        if amount is None:
            amount = raw.get("total")
        currency = raw.get("currency") or raw.get("currencyCode")
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        amount = raw
    if amount is None:
        for key in ("costAmount", "providerCost", "total_cost"):
            val = usage.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                amount = val
                break
    if amount is None:
        return None
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return None
    currency_text = str(currency or usage.get("currency") or "USD").strip() or "USD"
    return {
        "amount": float(amount),
        "currency": currency_text,
        "source": "provider",
        "providerAmount": float(amount),
    }


def build_event_id(*, request_id: str, message_id: str | None, status: str) -> str:
    req = (request_id or "").strip() or f"req_{uuid4().hex}"
    msg = (message_id or "").strip() or "nomsg"
    st = (status or "completed").strip() or "completed"
    return f"{req}:{msg}:{st}"


def build_generation_metadata(
    *,
    request_id: str,
    chat_id: str | None,
    message_id: str | None,
    provider: str | None,
    protocol: str | None,
    requested_model: str | None,
    resolved_model: str | None,
    usage: dict[str, Any] | None,
    started_at: str | None,
    first_token_latency_ms: int | None,
    total_duration_ms: int | None,
    streaming: bool,
    status: str = "completed",
) -> dict[str, Any]:
    tokens = usage_tokens_view(usage)
    cost = cost_from_usage(usage)
    call: dict[str, Any] = {
        "requestId": request_id,
        "provider": provider,
        "protocol": protocol,
        "resolvedModel": resolved_model,
        "status": status,
    }
    if tokens:
        call["usage"] = tokens
    if cost:
        call["cost"] = cost
    if total_duration_ms is not None:
        call["durationMs"] = total_duration_ms
    meta: dict[str, Any] = {
        "version": METADATA_VERSION,
        "requestId": request_id,
        "chatId": chat_id,
        "messageId": message_id,
        "provider": provider,
        "protocol": protocol,
        "requestedModel": requested_model,
        "resolvedModel": resolved_model,
        "startedAt": started_at or _now_iso(),
        "status": status,
        "nonStreaming": (not streaming),
        "calls": [call],
    }
    if first_token_latency_ms is not None:
        meta["firstTokenLatencyMs"] = first_token_latency_ms
    if total_duration_ms is not None:
        meta["totalDurationMs"] = total_duration_ms
    if tokens:
        meta["usage"] = tokens
    if cost:
        meta["cost"] = cost
    else:
        meta["cost"] = {"source": "unknown"}
    return meta


def _load_index() -> dict[str, Any]:
    path = _index_path()
    if not path.exists():
        return {
            "version": LEDGER_VERSION,
            "eventCount": 0,
            "lastEventId": None,
            "lastAppendedAt": None,
        }
    try:
        raw = read_json(path)
    except Exception:
        logger.exception("usage index unreadable; rebuilding counts from shards is deferred to T-808")
        return {
            "version": LEDGER_VERSION,
            "eventCount": 0,
            "lastEventId": None,
            "lastAppendedAt": None,
            "indexRebuiltPending": True,
        }
    if not isinstance(raw, dict):
        return {"version": LEDGER_VERSION, "eventCount": 0, "lastEventId": None, "lastAppendedAt": None}
    return raw


def _save_index(index: dict[str, Any]) -> None:
    write_json(_index_path(), index)


def enqueue_usage_repair(event: dict[str, Any], *, detail: str) -> None:
    payload = {
        "queuedAt": _now_iso(),
        "detail": detail,
        "event": event,
    }
    try:
        append_jsonl_object(_repair_path(), payload)
    except Exception:
        logger.exception("failed to enqueue usage repair record")


def append_usage_event(metadata: dict[str, Any], *, status: str | None = None) -> bool:
    """把 metadata 写成账本事件。同一 eventId 重复写入直接跳过。"""
    st = status or str(metadata.get("status") or "completed")
    event_id = metadata.get("eventId") or build_event_id(
        request_id=str(metadata.get("requestId") or ""),
        message_id=str(metadata.get("messageId") or "") or None,
        status=st,
    )
    event: dict[str, Any] = {
        "eventId": event_id,
        "version": LEDGER_VERSION,
        "requestId": metadata.get("requestId"),
        "chatId": metadata.get("chatId"),
        "messageId": metadata.get("messageId"),
        "provider": metadata.get("provider"),
        "protocol": metadata.get("protocol"),
        "requestedModel": metadata.get("requestedModel"),
        "resolvedModel": metadata.get("resolvedModel"),
        "usage": metadata.get("usage"),
        "cost": metadata.get("cost"),
        "startedAt": metadata.get("startedAt"),
        "firstTokenLatencyMs": metadata.get("firstTokenLatencyMs"),
        "totalDurationMs": metadata.get("totalDurationMs"),
        "status": st,
        "ts": _now_iso(),
    }
    try:
        written = append_jsonl_object(_shard_path(), event, unique_key="eventId")
    except Exception as exc:
        enqueue_usage_repair(event, detail=str(exc))
        raise AppError(
            code="usage_persist_failed",
            message="用量账本写入失败",
            detail=str(exc),
            source="usage.ledger",
            status_code=500,
            retryable=True,
            suggested_action="会话消息若已保存，可从 generationMetadata 修复账本；否则重试生成本轮",
        ) from exc
    if not written:
        return False
    try:
        index = _load_index()
        index["version"] = LEDGER_VERSION
        index["eventCount"] = int(index.get("eventCount") or 0) + 1
        index["lastEventId"] = event_id
        index["lastAppendedAt"] = event["ts"]
        _save_index(index)
    except Exception:
        logger.exception("usage index update failed after ledger append")
    return True
