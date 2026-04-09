"""
OmniVoice 本地进程托管模块

按 OmniVoice 文档通过 ``uvicorn omnivoice.api.server:app`` 启动本地 FastAPI 网关，
并在应用关闭时终止子进程。仅当预设启用托管启动（ttsOmniVoiceLocalManaged=True）时生效。
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

_process: subprocess.Popen | None = None
_managed_port: int | None = None


def is_running() -> bool:
    return _process is not None and _process.poll() is None


async def _health_poll(base_url: str, *, retries: int = 60, interval: float = 3.0) -> bool:
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
                    "omnivoice.api.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                f"python={python_executable} module=uvicorn omnivoice.api.server:app",
            )

    return (
        ["python", "-m", "uvicorn", "omnivoice.api.server:app", "--host", "127.0.0.1", "--port", str(port)],
        "python=python module=uvicorn omnivoice.api.server:app",
    )


async def start(
    repo_path: str,
    port: int = 8089,
    *,
    model_id: str = "k2-fsa/OmniVoice",
    device: str = "cuda:0",
) -> bool:
    """
    启动 OmniVoice 本地 FastAPI 网关子进程。

    如果端口已可访问（已有服务），跳过启动。
    返回 True 表示服务可用（无论是否新启动）。
    """
    global _process, _managed_port

    base_url = f"http://127.0.0.1:{port}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                logger.info("[OMNIVOICE] 端口 %d 已就绪，跳过启动", port)
                return True
    except Exception:
        pass

    if is_running():
        logger.info("[OMNIVOICE] 子进程已在运行 (pid=%s)", _process.pid if _process else None)
        return await _health_poll(base_url)

    repo = Path(repo_path)
    if not repo.is_dir():
        logger.error("[OMNIVOICE] 仓库路径不存在: %s", repo)
        return False

    cmd, resolved_from = _resolve_python_command(repo, port)
    logger.info("[OMNIVOICE] 启动: %s (%s)", " ".join(cmd), resolved_from)

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE

    env = os.environ.copy()
    apply_hf_cache_env(env)
    env["OMNIVOICE_MODEL"] = model_id.strip() or "k2-fsa/OmniVoice"
    normalized_device = device.strip()
    if normalized_device:
        env["OMNIVOICE_DEVICE"] = normalized_device
    else:
        env.pop("OMNIVOICE_DEVICE", None)

    _process = subprocess.Popen(
        cmd,
        cwd=str(repo),
        env=env,
        creationflags=creation_flags,
    )
    _managed_port = port

    ok = await _health_poll(base_url)
    if ok:
        logger.info("[OMNIVOICE] 服务已就绪 (pid=%d, port=%d)", _process.pid, port)
    else:
        logger.error("[OMNIVOICE] 健康检查超时，服务可能未正常启动")
        logger.error("[OMNIVOICE] 若已弹出独立控制台窗口，请直接查看 uvicorn / OmniVoice 的错误输出。")
    return ok


def stop() -> None:
    """终止托管的子进程。"""
    global _process, _managed_port

    if _process is None:
        return

    if _process.poll() is not None:
        logger.info("[OMNIVOICE] 子进程已退出 (code=%s)", _process.returncode)
        _process = None
        _managed_port = None
        return

    logger.info("[OMNIVOICE] 正在终止子进程 (pid=%d)…", _process.pid)
    try:
        if sys.platform == "win32":
            _process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            _process.terminate()
        _process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        logger.warning("[OMNIVOICE] 子进程未响应，强制 kill")
        _process.kill()
        _process.wait(timeout=5)
    except Exception:
        logger.exception("[OMNIVOICE] 终止子进程时出错")
    finally:
        _process = None
        _managed_port = None