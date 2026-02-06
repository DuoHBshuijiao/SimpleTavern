#!/usr/bin/env python3
"""
SimpleTavern 更新执行脚本（由后端 /api/update/run 触发）

用法: python update_runner.py <backend_pid> <repo_root>

步骤：
1. 结束占用 4173 端口的进程（前端）
2. 结束后端进程（backend_pid）
3. 结束后端进程的父进程（主终端）
4. 将 data/update/update.zip 解压并覆盖到仓库根目录
5. 删除 update.zip
6. 执行 deploy.bat（Windows）或 deploy.sh（Linux）
7. 退出
"""

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


def _get_pids_by_port(port: int) -> list[int]:
    """获取占用指定端口的进程 PID 列表（Windows netstat -ano）。"""
    pids = []
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if out.returncode != 0:
            return pids
        for line in out.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pids.append(int(parts[-1]))
                    except ValueError:
                        pass
    except Exception:
        pass
    return pids


def _get_parent_pid(pid: int) -> int | None:
    """获取指定进程的父进程 PID（Windows wmic）。"""
    try:
        out = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                f"ProcessId={pid}",
                "get",
                "ParentProcessId",
                "/format:csv",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if out.returncode != 0:
            return None
        lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
        if len(lines) >= 2:
            # CSV: Node,ParentProcessId,ProcessId
            parts = lines[1].split(",")
            if len(parts) >= 2:
                return int(parts[1])
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> None:
    """结束指定 PID 的进程（Windows taskkill）。"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        pass


def _kill_by_port(port: int) -> None:
    """结束占用端口的进程。"""
    for pid in _get_pids_by_port(port):
        _kill_pid(pid)
        time.sleep(0.5)


def main() -> None:
    if len(sys.argv) < 3:
        print("用法: python update_runner.py <backend_pid> <repo_root>")
        sys.exit(1)
    try:
        backend_pid = int(sys.argv[1])
    except ValueError:
        print("无效的 backend_pid")
        sys.exit(1)
    repo_root = Path(sys.argv[2]).resolve()
    if not repo_root.is_dir():
        print("无效的 repo_root")
        sys.exit(1)

    zip_path = repo_root / "data" / "update" / "update.zip"
    if not zip_path.is_file():
        print("未找到 data/update/update.zip")
        input("按 Enter 退出...")
        sys.exit(1)

    # 1. 结束前端（4173）
    _kill_by_port(4173)
    time.sleep(1)
    # 2. 结束后端
    _kill_pid(backend_pid)
    time.sleep(1)
    # 3. 结束主终端（后端父进程）
    parent = _get_parent_pid(backend_pid)
    if parent and parent != 0:
        _kill_pid(parent)
    time.sleep(0.5)

    # 4. 解压并覆盖
    tmp_extract = repo_root / "_update_tmp"
    try:
        tmp_extract.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_extract)
        top_dirs = [d for d in tmp_extract.iterdir() if d.is_dir()]
        if len(top_dirs) != 1:
            print("zip 结构异常，应为单一顶层目录")
            sys.exit(1)
        inner = top_dirs[0]
        for p in inner.rglob("*"):
            if p.is_file():
                rel = p.relative_to(inner)
                dest = repo_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
    finally:
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)

    # 5. 删除 zip
    try:
        zip_path.unlink()
    except Exception:
        pass

    # 6. 在新窗口触发 deploy，然后关闭自身
    if sys.platform == "win32":
        deploy = repo_root / "deploy.bat"
        if deploy.is_file():
            subprocess.Popen(
                ["cmd.exe", "/c", "deploy.bat"],
                cwd=str(repo_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
    else:
        deploy = repo_root / "deploy.sh"
        if deploy.is_file():
            subprocess.Popen(
                ["/bin/sh", str(deploy)],
                cwd=str(repo_root),
                start_new_session=True,
            )

    # 7. 退出，脚本窗口关闭
    sys.exit(0)


if __name__ == "__main__":
    main()
