"""
GLM-TTS 本地进程托管模块

在 Windows 上通过 PowerShell 调用 ``run_api_gpu.ps1`` 启动 GLM-TTS 本地 API，
并在应用关闭时终止子进程，防止僵尸 GPU 进程。

仅当用户在预设中勾选"由程序启动/托管"（ttsGlmLocalManaged=True）时生效。
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.storage import apply_hf_cache_env

logger = logging.getLogger(__name__)

_process: subprocess.Popen | None = None
_managed_port: int | None = None
_failure_count = 0
_last_error: dict[str, Any] | None = None
_last_success_at: str | None = None
_last_code: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _record_success() -> None:
    global _failure_count, _last_error, _last_success_at, _last_code
    _failure_count = 0
    _last_error = None
    _last_code = None
    _last_success_at = _now_iso()


def _record_failure(code: str, message: str, **extra: Any) -> None:
    global _failure_count, _last_error, _last_code
    _failure_count += 1
    _last_code = code
    _last_error = {"code": code, "message": message, **extra}


def get_health() -> dict[str, Any]:
    running = is_running()
    status = "ok"
    if _last_error is not None:
        status = "error"
    elif not running and _managed_port is not None:
        status = "stopped"
    return {
        "status": status,
        "running": running,
        "managedPort": _managed_port,
        "pid": _process.pid if _process is not None and running else None,
        "failureCount": _failure_count,
        "lastError": _last_error,
        "lastSuccessAt": _last_success_at,
        "code": _last_code,
    }


def note_reachable(*, port: int | None = None) -> None:
    """外部探测确认服务可达时清除历史失败态，避免误报。"""
    global _managed_port
    if port is not None:
        _managed_port = port
    _record_success()


def is_running() -> bool:
    return _process is not None and _process.poll() is None


async def _health_poll(base_url: str, *, retries: int = 40, interval: float = 3.0) -> bool:
    """轮询 /health 等待服务就绪。"""
    last_detail = "unreachable"
    async with httpx.AsyncClient(timeout=5) as client:
        for _ in range(retries):
            try:
                resp = await client.get(f"{base_url}/health")
                if resp.status_code == 200:
                    return True
                last_detail = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:
                last_detail = str(exc) or type(exc).__name__
            await asyncio.sleep(interval)
    return False


async def start(repo_path: str, port: int = 8088) -> bool:
    """
    启动 GLM-TTS 本地 API 子进程。

    如果端口已可访问（已有服务），跳过启动。
    返回 True 表示服务可用（无论是否新启动）。
    """
    global _process, _managed_port

    base_url = f"http://127.0.0.1:{port}"

    # 幂等：端口已可访问则跳过
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                logger.info("[GLM-TTS] 端口 %d 已就绪，跳过启动", port)
                _managed_port = port
                _record_success()
                return True
    except httpx.HTTPError:
        pass

    if is_running():
        logger.info("[GLM-TTS] 子进程已在运行 (pid=%s)", _process.pid if _process else None)
        ok = await _health_poll(base_url)
        if ok:
            _record_success()
        else:
            _record_failure("tts_local_health_unreachable", "health poll timed out while process already running")
        return ok

    repo = Path(repo_path)
    script = repo / "run_api_gpu.ps1"
    if not script.is_file():
        logger.error("[GLM-TTS] 启动脚本不存在: %s", script)
        _record_failure("tts_local_process_start_failed", f"startup script missing: {script}")
        return False

    if sys.platform != "win32":
        logger.warning("[GLM-TTS] 进程托管目前仅支持 Windows")
        _record_failure("tts_local_process_start_failed", "managed start is Windows-only")
        return False

    env = os.environ.copy()
    apply_hf_cache_env(env)
    env["GLMTTS_API_PORT"] = str(port)
    env["GLMTTS_API_HOST"] = "127.0.0.1"

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(script),
    ]

    logger.info("[GLM-TTS] 启动: %s (port=%d)", " ".join(cmd), port)
    try:
        _process = subprocess.Popen(
            cmd,
            cwd=str(repo),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE,
        )
    except OSError as exc:
        logger.exception("[GLM-TTS] 启动子进程失败")
        _record_failure("tts_local_process_start_failed", str(exc))
        _process = None
        return False
    _managed_port = port

    ok = await _health_poll(base_url)
    if ok:
        logger.info("[GLM-TTS] 服务已就绪 (pid=%d, port=%d)", _process.pid, port)
        _record_success()
    else:
        logger.error("[GLM-TTS] 健康检查超时，服务可能未正常启动")
        logger.error(
            "[GLM-TTS] 若已弹出独立控制台窗口，请在该窗口中查看 run_api_gpu / 下游进程的报错输出。"
        )
        # 仅由 start() 记一次失败，避免与 _health_poll 重复累加
        _record_failure("tts_local_process_start_failed", "health check timed out after start")
    return ok


def stop() -> None:
    """终止托管的子进程。"""
    global _process, _managed_port

    if _process is None:
        return

    if _process.poll() is not None:
        logger.info("[GLM-TTS] 子进程已退出 (code=%s)", _process.returncode)
        _process = None
        _managed_port = None
        return

    logger.info("[GLM-TTS] 正在终止子进程 (pid=%d)…", _process.pid)
    try:
        if sys.platform == "win32":
            _process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _process.terminate()
        _process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        logger.warning("[GLM-TTS] 子进程未响应，强制 kill")
        _process.kill()
        _process.wait(timeout=5)
    except Exception as exc:
        logger.exception("[GLM-TTS] 终止子进程时出错")
        _record_failure("tts_local_process_stop_failed", str(exc))
    finally:
        _process = None
        _managed_port = None
