"""
Qwen3-TTS 本地进程托管模块

按用户文档通过 ``uvicorn qwen_tts.gateway.app:app`` 启动本地 FastAPI 网关，
并在应用关闭时终止子进程。仅当预设启用托管启动（ttsQwen3LocalManaged=True）时生效。

支持多端口：CustomVoice 与 Base 各占一进程（一进程一模型）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

import httpx

from app.storage import apply_hf_cache_env

logger = logging.getLogger(__name__)

_processes: dict[int, subprocess.Popen] = {}


def is_running() -> bool:
    return any(p.poll() is None for p in _processes.values())


async def _health_poll(base_url: str, *, retries: int = 40, interval: float = 3.0) -> bool:
    """轮询 /health 等待服务就绪。"""
    async with httpx.AsyncClient(timeout=5) as client:
        for _ in range(retries):
            try:
                resp = await client.get(f"{base_url}/health")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
    return False


def _resolve_python_command(repo: Path, port: int) -> tuple[list[str], str]:
    python_candidates = []
    if sys.platform == "win32":
        python_candidates.extend(
            [
                repo / ".venv" / "Scripts" / "python.exe",
                repo / "venv" / "Scripts" / "python.exe",
            ]
        )
    else:
        python_candidates.extend(
            [
                repo / ".venv" / "bin" / "python",
                repo / "venv" / "bin" / "python",
            ]
        )
    python_candidates.append(Path(sys.executable))

    for python_executable in python_candidates:
        if python_executable.is_file():
            return (
                [
                    str(python_executable),
                    "-m",
                    "uvicorn",
                    "qwen_tts.gateway.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                f"python={python_executable} module=uvicorn qwen_tts.gateway.app:app",
            )

    return (
        ["python", "-m", "uvicorn", "qwen_tts.gateway.app:app", "--host", "127.0.0.1", "--port", str(port)],
        "python=python module=uvicorn qwen_tts.gateway.app:app",
    )


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    logger.info("[QWEN3-TTS] 正在终止子进程 (pid=%d)…", proc.pid)
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        logger.warning("[QWEN3-TTS] 子进程未响应，强制 kill")
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        logger.exception("[QWEN3-TTS] 终止子进程时出错")


async def start(
    repo_path: str,
    port: int = 8000,
    *,
    model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device: str = "cuda:0",
) -> bool:
    """
    启动指定端口上的 Qwen3-TTS 本地 FastAPI 网关子进程。

    如果该端口已可访问（已有服务），跳过启动。
    返回 True 表示服务可用（无论是否新启动）。
    """
    global _processes

    base_url = f"http://127.0.0.1:{port}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                logger.info("[QWEN3-TTS] 端口 %d 已就绪，跳过启动", port)
                return True
    except Exception:
        pass

    existing = _processes.get(port)
    if existing is not None:
        if existing.poll() is None:
            logger.info("[QWEN3-TTS] 本应用已在端口 %d 托管子进程，等待就绪", port)
            return await _health_poll(base_url)
        del _processes[port]

    repo = Path(repo_path)
    if not repo.is_dir():
        logger.error("[QWEN3-TTS] 仓库路径不存在: %s", repo)
        return False

    cmd, resolved_from = _resolve_python_command(repo, port)
    logger.info("[QWEN3-TTS] 启动: %s (%s)", " ".join(cmd), resolved_from)

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE

    env = os.environ.copy()
    apply_hf_cache_env(env)
    env["QWEN_TTS_MODEL_PATH"] = model_id.strip() or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    env["QWEN_TTS_DEVICE"] = device.strip() or "cuda:0"

    proc = subprocess.Popen(
        cmd,
        cwd=str(repo),
        env=env,
        creationflags=creation_flags,
    )
    _processes[port] = proc

    ok = await _health_poll(base_url)
    if ok:
        logger.info("[QWEN3-TTS] 服务已就绪 (pid=%d, port=%d)", proc.pid, port)
    else:
        logger.error("[QWEN3-TTS] 健康检查超时，服务可能未正常启动 (port=%d)", port)
        logger.error("[QWEN3-TTS] 若已弹出独立控制台窗口，请直接查看 uvicorn / gateway 的错误输出。")
    return ok


def stop() -> None:
    """终止所有托管的 Qwen3-TTS 子进程。"""
    global _processes

    ports = list(_processes.keys())
    for port in ports:
        proc = _processes.pop(port, None)
        if proc is None:
            continue
        if proc.poll() is not None:
            logger.info("[QWEN3-TTS] 端口 %d 子进程已退出 (code=%s)", port, proc.returncode)
            continue
        _terminate_process(proc)
