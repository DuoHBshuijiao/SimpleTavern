#!/usr/bin/env python3
"""并行沙箱：独立 data-sandbox/ + 9181/9191，不占用生产 9081/9091 与 data/。"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_PORT = 9191
FRONTEND_PORT = 9181
BACKEND_HOST = "127.0.0.1"
FRONTEND_HOST = "127.0.0.1"


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def venv_python(root: Path) -> Path:
    if platform.system() == "Windows":
        return root / "venv" / "Scripts" / "python.exe"
    return root / "venv" / "bin" / "python"


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def wait_http(url: str, timeout_sec: float = 45.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.4)
    return False


def seed_settings(prod_data: Path, sandbox_data: Path, refresh: bool) -> str:
    sandbox_data.mkdir(parents=True, exist_ok=True)
    src = prod_data / "settings.json"
    dst = sandbox_data / "settings.json"
    if not src.exists():
        return "生产 data/settings.json 不存在，沙箱将使用后端默认设置"
    if dst.exists() and not refresh:
        return f"保留已有 {dst}"
    shutil.copy2(src, dst)
    return f"已复制 settings.json -> {dst}"


def stop_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def frontend_command() -> list[str]:
    if platform.system() == "Windows":
        return [
            "cmd.exe",
            "/c",
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            FRONTEND_HOST,
            "--port",
            str(FRONTEND_PORT),
            "--strictPort",
        ]
    npm = shutil.which("npm") or "npm"
    return [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        FRONTEND_HOST,
        "--port",
        str(FRONTEND_PORT),
        "--strictPort",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="启动并行沙箱（独立 data 与端口）")
    parser.add_argument(
        "--refresh-settings",
        action="store_true",
        help="强制用生产 data/settings.json 覆盖沙箱 settings.json",
    )
    args = parser.parse_args()

    root = repo_root()
    backend_dir = root / "backend"
    frontend_dir = root / "frontend"
    prod_data = root / "data"
    sandbox_data = root / "data-sandbox"
    py = venv_python(root)

    if not py.exists():
        print(f"[ERROR] 找不到虚拟环境 Python: {py}", file=sys.stderr)
        print("请先运行 deploy.py 完成安装。", file=sys.stderr)
        return 1
    if not (frontend_dir / "node_modules").exists():
        print(f"[ERROR] 找不到前端依赖: {frontend_dir / 'node_modules'}", file=sys.stderr)
        print("请先运行 deploy.py 或在 frontend 目录执行 npm install。", file=sys.stderr)
        return 1

    for name, port in (("后端", BACKEND_PORT), ("前端", FRONTEND_PORT)):
        if port_in_use(BACKEND_HOST, port):
            print(
                f"[ERROR] 沙箱{name}端口 {BACKEND_HOST}:{port} 已被占用，未结束生产 9081/9091。",
                file=sys.stderr,
            )
            return 1

    seed_msg = seed_settings(prod_data, sandbox_data, args.refresh_settings)
    print(f"[INFO] {seed_msg}")
    print("[INFO] 不复制角色/会话/世界书/头像/OAuth token/TTS 缓存/字体/背景图。")
    print("[INFO] OAuth 需在沙箱内重新登录；设置里若指向未复制的字体或背景图会回退默认。")

    env = os.environ.copy()
    env["SIMPLETAVERN_DATA_DIR"] = str(sandbox_data)
    env["SIMPLETAVERN_FRONTEND_PORT"] = str(FRONTEND_PORT)
    env["SIMPLETAVERN_API_PROXY"] = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None
    try:
        print(f"[INFO] 启动沙箱后端 {BACKEND_HOST}:{BACKEND_PORT} data={sandbox_data}")
        backend_proc = subprocess.Popen(
            [
                str(py),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                BACKEND_HOST,
                "--port",
                str(BACKEND_PORT),
                "--timeout-graceful-shutdown",
                "3",
            ],
            cwd=backend_dir,
            env=env,
        )
        health_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"
        if not wait_http(health_url):
            print(f"[ERROR] 后端未在时限内响应 {health_url}", file=sys.stderr)
            return 1
        print(f"[SUCCESS] 后端健康检查通过: {health_url}")

        print(f"[INFO] 启动沙箱前端 {FRONTEND_HOST}:{FRONTEND_PORT} 代理 {env['SIMPLETAVERN_API_PROXY']}")
        frontend_proc = subprocess.Popen(
            frontend_command(),
            cwd=frontend_dir,
            env=env,
        )
        front_url = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
        if not wait_http(front_url, timeout_sec=60.0):
            print(f"[ERROR] 前端未在时限内响应 {front_url}", file=sys.stderr)
            return 1

        print()
        print("沙箱已就绪（生产 9081/9091 与 data/ 未改动）")
        print(f"  前端: {front_url}")
        print(f"  后端: {health_url}")
        print(f"  数据: {sandbox_data}")
        print("浏览器点按请打开上述前端地址。Ctrl+C 结束沙箱进程。")
        print()

        while True:
            if backend_proc.poll() is not None:
                print(f"[ERROR] 后端已退出，code={backend_proc.returncode}", file=sys.stderr)
                return backend_proc.returncode or 1
            if frontend_proc.poll() is not None:
                print(f"[ERROR] 前端已退出，code={frontend_proc.returncode}", file=sys.stderr)
                return frontend_proc.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[INFO] 正在停止沙箱...")
        return 0
    finally:
        stop_tree(frontend_proc)
        stop_tree(backend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
