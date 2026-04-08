"""
TTS 缓存巡检服务

后台每 30s 检查 tts_cache 目录占用，超过上限时按旧到新删除约一半文件。
提供缓存统计与清空接口。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from app.storage import get_tts_cache_dir, load_settings

logger = logging.getLogger(__name__)

PATROL_INTERVAL_SECONDS = 30


class TtsCachePatrol:
    """单例巡检任务，由 lifespan 启动/停止。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        # 最近一次巡检结果（权威数据源）
        self.used_bytes: int = 0
        self.limit_bytes: int = 200 * 1024 * 1024
        self.last_patrol_at: str = ""
        self.pruned_files: int = 0

    async def start(self) -> None:
        if self._task is None or self._task.done():
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
                await self._patrol_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[TTS][cache] patrol error")
            await asyncio.sleep(PATROL_INTERVAL_SECONDS)

    async def _patrol_once(self) -> None:
        settings = load_settings()
        if not settings.ttsEnabled:
            self.used_bytes = 0
            self.last_patrol_at = _now_iso()
            self.pruned_files = 0
            return

        self.limit_bytes = settings.ttsAudioCacheLimitMb * 1024 * 1024
        cache_dir = get_tts_cache_dir()

        # 在线程中执行 IO 密集操作
        loop = asyncio.get_running_loop()
        used, pruned = await loop.run_in_executor(
            None, self._scan_and_prune, cache_dir, self.limit_bytes
        )
        self.used_bytes = used
        self.pruned_files = pruned
        self.last_patrol_at = _now_iso()

    @staticmethod
    def _scan_and_prune(cache_dir: Path, limit_bytes: int) -> tuple[int, int]:
        """扫描目录，超限时删除约一半旧文件。返回 (当前占用, 删除文件数)。"""
        if not cache_dir.exists():
            return 0, 0

        entries: list[tuple[Path, float, int]] = []
        total = 0
        for f in cache_dir.iterdir():
            if f.is_file():
                try:
                    st = f.stat()
                    entries.append((f, st.st_mtime, st.st_size))
                    total += st.st_size
                except OSError:
                    continue

        if total <= limit_bytes:
            return total, 0

        # 按修改时间排序（最旧在前）
        entries.sort(key=lambda x: x[1])
        target = total // 2  # 删到约一半
        deleted_size = 0
        pruned = 0
        for path, _mtime, size in entries:
            if deleted_size >= target:
                break
            try:
                path.unlink(missing_ok=True)
                deleted_size += size
                pruned += 1
            except OSError:
                continue

        return total - deleted_size, pruned

    def get_stats(self) -> dict:
        return {
            "usedBytes": self.used_bytes,
            "limitBytes": self.limit_bytes,
            "lastPatrolAt": self.last_patrol_at,
            "prunedFiles": self.pruned_files,
        }

    async def clear_all(self) -> dict:
        """清空所有缓存文件。"""
        cache_dir = get_tts_cache_dir()
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, self._clear_dir, cache_dir)
        self.used_bytes = 0
        self.pruned_files = count
        self.last_patrol_at = _now_iso()
        return self.get_stats()

    @staticmethod
    def _clear_dir(cache_dir: Path) -> int:
        count = 0
        if not cache_dir.exists():
            return count
        for f in cache_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink(missing_ok=True)
                    count += 1
                except OSError:
                    continue
        return count


# 单例
tts_cache_patrol = TtsCachePatrol()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
