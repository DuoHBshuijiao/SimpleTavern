"""
出站 HTTP 请求日志查看 API

- GET  /api/http-log          列表（默认最近 30 分钟元数据，从旧到新）
- GET  /api/http-log/{id}     单条完整记录
- DELETE /api/http-log        清空全部日志

日志仅保留最近 30 分钟，由 services.http_log_sweeper 后台每 30s 清理。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.http_log import (
    RETENTION_MINUTES,
    clear_all,
    list_recent,
    load_detail,
)

router = APIRouter(tags=["http-log"])


@router.get("/http-log")
def get_http_log_list(
    minutes: int = Query(default=RETENTION_MINUTES, ge=1, le=RETENTION_MINUTES),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict:
    """返回最近 N 分钟的记录元数据；从旧到新排序，便于前端自然追加。"""
    rows = list_recent(since_minutes=minutes, limit=limit)
    return {
        "retentionMinutes": RETENTION_MINUTES,
        "count": len(rows),
        "items": rows,
    }


@router.get("/http-log/{record_id}")
def get_http_log_detail(record_id: str) -> dict:
    """返回单条完整记录（含 request/response 原始内容）。"""
    detail = load_detail(record_id)
    if not detail:
        raise HTTPException(status_code=404, detail="record not found")
    return detail


@router.delete("/http-log")
def delete_http_log() -> dict:
    """清空全部日志。"""
    removed = clear_all()
    return {"ok": True, "removedFiles": removed}
