#!/usr/bin/env python3
"""
SimpleTavern 更新执行脚本（由后端 /api/update/run 触发）

用法: python update_runner.py <backend_pid> <repo_root>

步骤：
1. 结束占用 9081 端口的进程（前端）
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


def _countdown_and_exit(exit_code: int, message: str = "") -> None:
    """无论成功或失败，倒计时 10 秒后退出，便于查看输出或排查问题。"""
    if message:
        print(message)
    print("\n10 秒后关闭此窗口...")
    for i in range(10, 0, -1):
        print(f"  {i} ...", flush=True)
        time.sleep(1)
    sys.exit(exit_code)


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


def _kill_pid(pid: int, kill_tree: bool = True) -> None:
    """结束指定 PID 的进程（Windows taskkill）。
    kill_tree=False 时仅杀该进程，不杀子进程。结束后端时必须用 False，否则会连本更新脚本（后端→cmd→本进程）一起杀掉。
    """
    try:
        args = ["taskkill", "/PID", str(pid), "/F"]
        if kill_tree:
            args.insert(-1, "/T")
        subprocess.run(
            args,
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
        _countdown_and_exit(1)
    try:
        backend_pid = int(sys.argv[1])
    except ValueError:
        print("无效的 backend_pid")
        _countdown_and_exit(1)
    repo_root = Path(sys.argv[2]).resolve()
    if not repo_root.is_dir():
        print("无效的 repo_root")
        _countdown_and_exit(1)

    zip_path = repo_root / "data" / "update" / "update.zip"
    if not zip_path.is_file():
        print("未找到 data/update/update.zip")
        _countdown_and_exit(1)

    # 先获取后端父进程 PID（主终端 = 运行 deploy 的进程），结束后端后无法再查询
    main_window_pid = _get_parent_pid(backend_pid)
    if not main_window_pid or main_window_pid == 0:
        main_window_pid = None
    # 若主终端是 python（如 deploy.py），再取其父进程（如运行 deploy.bat 的 cmd），以便一并关闭主窗口
    grandparent_pid = _get_parent_pid(main_window_pid) if main_window_pid else None
    if not grandparent_pid or grandparent_pid == 0:
        grandparent_pid = None

    # 1. 结束前端（9081）
    _kill_by_port(9081)
    time.sleep(1)
    # 2. 结束后端（仅杀后端进程，不杀子进程，否则会连本更新脚本所在 cmd/python 一起杀掉）
    _kill_pid(backend_pid, kill_tree=False)
    time.sleep(1)
    # 3. 结束主终端（后端父进程，即运行 deploy 的窗口；若有祖父进程如 cmd 也一并结束）
    if main_window_pid:
        _kill_pid(main_window_pid)
    time.sleep(0.3)
    if grandparent_pid and grandparent_pid != os.getpid():
        _kill_pid(grandparent_pid)
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
            _countdown_and_exit(1)
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

    # 7. 成功完成，倒计时后退出
    _countdown_and_exit(0, "更新已完成，deploy 已在新窗口启动。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n更新过程发生错误: {e}", flush=True)
        import traceback
        traceback.print_exc()
        _countdown_and_exit(1, "请根据上方错误信息排查问题。")
