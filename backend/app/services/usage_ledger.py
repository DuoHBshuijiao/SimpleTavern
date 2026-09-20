"""消息 generation metadata 与 append-only usage ledger（T-807 / T-808 / T-813）。

路径：
- ``data/usage/YYYY-MM.jsonl``：按月分片，一行一个事件
- ``data/usage/usage_index.json``：计数与最近 eventId
- ``data/usage/repair.jsonl``：账本写入失败时的可修复队列

定价引擎（T-808）在写入 metadata 时补本地估算；云端 cost 不被覆盖。
密钥与敏感字段不得进入账本（T-813）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterator
from uuid import uuid4

from app.errors import AppError, redact_sensitive_text
from app.services.pricing import estimate_cost_from_usage, merge_cost
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


_COST_ALLOWLIST = (
    "amount",
    "currency",
    "source",
    "providerAmount",
    "estimatedAmount",
    "pricingRuleId",
)
_EVENT_ALLOWLIST = (
    "eventId",
    "version",
    "requestId",
    "chatId",
    "messageId",
    "provider",
    "protocol",
    "requestedModel",
    "resolvedModel",
    "usage",
    "cost",
    "startedAt",
    "firstTokenLatencyMs",
    "totalDurationMs",
    "status",
    "ts",
)


def _sanitize_cost(cost: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cost, dict) or not cost:
        return None
    out: dict[str, Any] = {}
    for key in _COST_ALLOWLIST:
        if key not in cost:
            continue
        val = cost[key]
        if isinstance(val, str):
            out[key] = redact_sensitive_text(val, max_chars=200)
        else:
            out[key] = val
    return out or None


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _EVENT_ALLOWLIST:
        if key not in event:
            continue
        val = event[key]
        if key == "usage" and isinstance(val, dict):
            out[key] = usage_tokens_view(val)
        elif key == "cost" and isinstance(val, dict):
            out[key] = _sanitize_cost(val)
        elif isinstance(val, str):
            out[key] = redact_sensitive_text(val, max_chars=500)
        else:
            out[key] = val
    return out


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
    provider_cost = cost_from_usage(usage)
    estimated = estimate_cost_from_usage(
        tokens,
        provider=provider,
        resolved_model=resolved_model,
        requested_model=requested_model,
    )
    cost = _sanitize_cost(merge_cost(provider_cost, estimated)) or {"source": "unknown"}
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
    meta["cost"] = cost
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
        logger.exception("usage index unreadable; rebuilding from shards")
        rebuilt = rebuild_index()
        rebuilt["indexRebuilt"] = True
        return rebuilt
    if not isinstance(raw, dict):
        return {"version": LEDGER_VERSION, "eventCount": 0, "lastEventId": None, "lastAppendedAt": None}
    return raw


def _save_index(index: dict[str, Any]) -> None:
    write_json(_index_path(), index)


def enqueue_usage_repair(event: dict[str, Any], *, detail: str) -> None:
    payload = {
        "queuedAt": _now_iso(),
        "detail": redact_sensitive_text(detail),
        "event": _sanitize_event(event),
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
    event = _sanitize_event(
        {
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
    )
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


def _iter_shard_paths() -> list[Any]:
    directory = get_usage_dir()
    if not directory.exists():
        return []
    paths = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".jsonl" and p.name not in {_REPAIR_NAME}
    ]
    return sorted(paths)


def _parse_event_line(raw: str) -> dict[str, Any] | None:
    line = raw.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def iter_ledger_events(
    *,
    chat_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    status: str | None = None,
) -> Iterator[dict[str, Any]]:
    """按时间升序产出账本事件；过滤条件均为可选。"""
    chat_filter = (chat_id or "").strip() or None
    status_filter = (status or "").strip() or None
    since_text = (since or "").strip() or None
    until_text = (until or "").strip() or None
    for path in _iter_shard_paths():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    event = _parse_event_line(raw)
                    if event is None:
                        continue
                    if chat_filter and str(event.get("chatId") or "") != chat_filter:
                        continue
                    if status_filter and str(event.get("status") or "") != status_filter:
                        continue
                    ts = str(event.get("ts") or event.get("startedAt") or "")
                    if since_text and ts and ts < since_text:
                        continue
                    if until_text and ts and ts > until_text:
                        continue
                    yield _sanitize_event(event)
        except OSError:
            logger.exception("usage shard unreadable: %s", path)


def rebuild_index() -> dict[str, Any]:
    """从月分片重建 usage_index.json（损坏或丢失时使用）。"""
    count = 0
    last_id = None
    last_ts = None
    seen: set[str] = set()
    for event in iter_ledger_events():
        event_id = str(event.get("eventId") or "")
        if event_id:
            if event_id in seen:
                continue
            seen.add(event_id)
        count += 1
        last_id = event_id or last_id
        last_ts = event.get("ts") or last_ts
    index = {
        "version": LEDGER_VERSION,
        "eventCount": count,
        "lastEventId": last_id,
        "lastAppendedAt": last_ts,
        "rebuiltAt": _now_iso(),
    }
    try:
        _save_index(index)
    except Exception:
        logger.exception("usage index rebuild save failed")
    return index


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def summarize_ledger_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """会话/全局汇总。未知成本不计 0。"""
    total_input = 0.0
    total_output = 0.0
    total_cache_read = 0.0
    total_cache_write = 0.0
    request_count = 0
    completed = 0
    failed = 0
    cancelled = 0
    billable = 0
    billable_input = 0.0
    billable_output = 0.0
    ttfts: list[float] = []
    durations: list[float] = []
    costs_by_currency: dict[str, dict[str, float]] = {}
    unknown_cost_count = 0

    for event in events:
        request_count += 1
        st = str(event.get("status") or "completed")
        if st == "failed":
            failed += 1
        elif st == "cancelled":
            cancelled += 1
        else:
            completed += 1
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        inp = _num(usage.get("inputTokens"))
        out = _num(usage.get("outputTokens"))
        cread = _num(usage.get("cacheReadInputTokens"))
        cwrite = _num(usage.get("cacheWriteInputTokens"))
        if inp is not None:
            total_input += inp
        if out is not None:
            total_output += out
        if cread is not None:
            total_cache_read += cread
        if cwrite is not None:
            total_cache_write += cwrite
        if st == "completed" and (inp is not None or out is not None):
            billable += 1
            billable_input += inp or 0.0
            billable_output += out or 0.0
        ttft = _num(event.get("firstTokenLatencyMs"))
        if ttft is not None:
            ttfts.append(ttft)
        dur = _num(event.get("totalDurationMs"))
        if dur is not None:
            durations.append(dur)
        cost = event.get("cost") if isinstance(event.get("cost"), dict) else {}
        source = str(cost.get("source") or "unknown")
        amount = _num(cost.get("amount"))
        currency = str(cost.get("currency") or "USD")
        if source == "provider" and amount is not None:
            bucket = costs_by_currency.setdefault(
                currency, {"provider": 0.0, "estimated": 0.0, "total": 0.0}
            )
            bucket["provider"] += amount
            bucket["total"] += amount
            estimated_amount = _num(cost.get("estimatedAmount"))
            if estimated_amount is not None:
                bucket["estimated"] += estimated_amount
        elif source == "estimated" and amount is not None:
            bucket = costs_by_currency.setdefault(
                currency, {"provider": 0.0, "estimated": 0.0, "total": 0.0}
            )
            bucket["estimated"] += amount
            bucket["total"] += amount
        else:
            unknown_cost_count += 1

    ttfts.sort()
    durations.sort()
    cache_hit_rate = None
    denom = total_input + total_cache_read
    if denom > 0 and total_cache_read > 0:
        cache_hit_rate = total_cache_read / denom

    return {
        "requestCount": request_count,
        "completedCount": completed,
        "failedCount": failed,
        "cancelledCount": cancelled,
        "inputTokens": total_input,
        "outputTokens": total_output,
        "avgInputTokens": (billable_input / billable) if billable else None,
        "avgOutputTokens": (billable_output / billable) if billable else None,
        "cacheReadInputTokens": total_cache_read,
        "cacheWriteInputTokens": total_cache_write,
        "cacheHitRate": cache_hit_rate,
        "costByCurrency": costs_by_currency,
        "unknownCostCount": unknown_cost_count,
        "avgFirstTokenLatencyMs": (sum(ttfts) / len(ttfts)) if ttfts else None,
        "p50FirstTokenLatencyMs": _percentile(ttfts, 0.50),
        "p95FirstTokenLatencyMs": _percentile(ttfts, 0.95),
        "avgTotalDurationMs": (sum(durations) / len(durations)) if durations else None,
        "p50TotalDurationMs": _percentile(durations, 0.50),
        "p95TotalDurationMs": _percentile(durations, 0.95),
    }


def summarize_ledger_by_model(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        key = (
            str(event.get("provider") or ""),
            str(event.get("protocol") or ""),
            str(event.get("resolvedModel") or event.get("requestedModel") or ""),
        )
        groups.setdefault(key, []).append(event)
    rows: list[dict[str, Any]] = []
    for (provider, protocol, model), group in groups.items():
        summary = summarize_ledger_events(group)
        rows.append(
            {
                "provider": provider or None,
                "protocol": protocol or None,
                "resolvedModel": model or None,
                **summary,
            }
        )
    rows.sort(key=lambda r: str(r.get("resolvedModel") or ""))
    return rows

