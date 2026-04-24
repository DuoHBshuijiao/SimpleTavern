"""
HTTP 请求日志滚动清理服务

启动时先跑一次清理，然后每 30 秒批量扫描一次 data/http_log：
- 删除时间戳早于 30 分钟的行；
- 若整个分片文件都过期，整文件删除；
- 出错仅记录日志，不影响主应用。

由 main.py lifespan 启动 / 停止。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from app.services.http_log import RETENTION_MINUTES, get_http_log_dir

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 30


class HttpLogSweeper:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("[http_log] startup sweep failed")
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
                await self._sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[http_log] sweep error")

    async def _sweep_once(self) -> None:
        await asyncio.to_thread(_sweep_blocking)


def _sweep_blocking() -> None:
    d = get_http_log_dir()
    if not d.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=RETENTION_MINUTES)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    # 分片名形如 2026-04-24-12.jsonl；早于当前小时 - 1 直接整文件删除（粗粒度快路径）
    safe_shard_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=RETENTION_MINUTES + 60)).strftime(
        "%Y-%m-%d-%H"
    )

    for shard in list(d.iterdir()):
        if not (shard.is_file() and shard.name.endswith(".jsonl")):
            continue
        base = shard.stem
        try:
            if base < safe_shard_cutoff:
                shard.unlink(missing_ok=True)
                continue
        except Exception:
            logger.exception("[http_log] failed to unlink stale shard %s", shard)

        # 精细：逐行过滤，重写
        try:
            kept: list[str] = []
            removed = 0
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.rstrip("\n")
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                    except Exception:
                        continue
                    ts_ms = int(obj.get("tsMs") or 0)
                    if ts_ms and ts_ms < cutoff_ms:
                        removed += 1
                        continue
                    kept.append(s)
            if not kept:
                shard.unlink(missing_ok=True)
                continue
            if removed == 0:
                continue
            tmp = shard.with_suffix(shard.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + "\n")
            tmp.replace(shard)
        except Exception:
            logger.exception("[http_log] failed to rewrite shard %s", shard)


http_log_sweeper = HttpLogSweeper()
