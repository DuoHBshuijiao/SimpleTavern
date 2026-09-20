"""用量汇总与本地价格表（T-808）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError
from app.chat_path_index import lookup_chat_path
from app.services.pricing import list_pricing_rules, upsert_user_pricing_rule
from app.services.usage_ledger import (
    iter_ledger_events,
    summarize_ledger_by_model,
    summarize_ledger_events,
)


router = APIRouter(tags=["usage"])

UsageScope = Literal["chat", "global"]


class PricingRuleUpsert(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str | None = None
    canonicalModelId: str | None = None
    aliases: list[str] = Field(default_factory=list)
    regexAliases: list[str] = Field(default_factory=list)
    inputPerMillion: float | None = None
    outputPerMillion: float | None = None
    cacheReadPerMillion: float | None = None
    cacheWritePerMillion: float | None = None
    currency: str = "USD"
    enabled: bool = True
    effectiveFrom: str | None = None
    effectiveTo: str | None = None
    sourceUrl: str | None = None


def _since_from_range(range_key: str | None, since: str | None) -> str | None:
    if (since or "").strip():
        return since.strip()
    key = (range_key or "all").strip().lower()
    now = datetime.now(timezone.utc).astimezone()
    if key in {"7d", "7"}:
        return (now - timedelta(days=7)).isoformat()
    if key in {"30d", "30"}:
        return (now - timedelta(days=30)).isoformat()
    if key in {"month", "this_month"}:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    return None


def _collect_events(
    *,
    scope: str,
    chat_id: str | None,
    range_key: str | None,
    since: str | None,
    until: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    scope_norm = (scope or "global").strip().lower()
    if scope_norm not in {"chat", "global"}:
        raise AppError(
            code="request_validation_failed",
            message="scope 必须是 chat 或 global",
            source="usage.api",
            status_code=422,
        )
    cid = (chat_id or "").strip() or None
    if scope_norm == "chat":
        if not cid:
            raise AppError(
                code="request_validation_failed",
                message="会话统计需要 chatId",
                source="usage.api",
                status_code=422,
                suggested_action="打开一个会话后再查看「当前会话」用量，或改用全局统计",
            )
        if lookup_chat_path(cid) is None:
            raise AppError(
                code="chat_not_found",
                message="会话不存在",
                detail=cid,
                source="usage.api",
                status_code=404,
            )
    since_text = _since_from_range(range_key, since)
    return list(
        iter_ledger_events(
            chat_id=cid if scope_norm == "chat" else None,
            since=since_text,
            until=(until or "").strip() or None,
            status=(status or "").strip() or None,
        )
    )


@router.get("/usage/summary")
def usage_summary(
    scope: UsageScope = Query(default="global"),
    chatId: str | None = Query(default=None),
    range: str | None = Query(default="all"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
) -> dict[str, Any]:
    events = _collect_events(
        scope=scope,
        chat_id=chatId,
        range_key=range,
        since=since,
        until=until,
        status=None,
    )
    summary = summarize_ledger_events(events)
    return {
        "ok": True,
        "scope": scope,
        "chatId": chatId if scope == "chat" else None,
        "range": range or "all",
        "eventCount": len(events),
        "summary": summary,
    }


@router.get("/usage/models")
def usage_models(
    scope: UsageScope = Query(default="global"),
    chatId: str | None = Query(default=None),
    range: str | None = Query(default="all"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
) -> dict[str, Any]:
    events = _collect_events(
        scope=scope,
        chat_id=chatId,
        range_key=range,
        since=since,
        until=until,
        status=None,
    )
    return {
        "ok": True,
        "scope": scope,
        "chatId": chatId if scope == "chat" else None,
        "range": range or "all",
        "models": summarize_ledger_by_model(events),
    }


@router.get("/usage/events")
def usage_events(
    scope: UsageScope = Query(default="global"),
    chatId: str | None = Query(default=None),
    range: str | None = Query(default="all"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    events = _collect_events(
        scope=scope,
        chat_id=chatId,
        range_key=range,
        since=since,
        until=until,
        status=status,
    )
    events.sort(key=lambda e: str(e.get("ts") or e.get("startedAt") or ""), reverse=True)
    total = len(events)
    page = events[offset : offset + limit]
    return {
        "ok": True,
        "scope": scope,
        "chatId": chatId if scope == "chat" else None,
        "range": range or "all",
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": page,
    }


@router.get("/pricing/rules")
def get_pricing_rules() -> dict[str, Any]:
    payload = list_pricing_rules()
    payload["ok"] = True
    return payload


@router.put("/pricing/rules/{rule_id}")
def put_pricing_rule(rule_id: str, body: PricingRuleUpsert) -> dict[str, Any]:
    rule = upsert_user_pricing_rule(rule_id, body.model_dump(exclude_none=False))
    return {"ok": True, "rule": rule}
