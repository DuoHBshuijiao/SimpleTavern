"""
更新检查与安装路由模块

提供检查云端版本、下载更新包、触发更新脚本的 API。
- GET /api/update/check: 检查是否有新版本
- POST /api/update/download: 下载指定 tag 的源码 zip 到 data/update
- POST /api/update/run: 触发根目录更新脚本（关闭前后端与主终端、解压覆盖、执行 deploy.bat）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from app.storage import get_repo_root, get_update_dir

router = APIRouter(tags=["update"])

CURRENT_VERSION = "v0.265"
GITHUB_REPO = "DuoHBshuijiao/SimpleTavern"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_version(tag: str) -> tuple[int, ...]:
    """举例：将 v0.228 解析为 (0, 228)，用于比较。"""
    tag = (tag or "").strip().lstrip("v")
    parts = re.findall(r"\d+", tag)
    return tuple(int(p) for p in parts) if parts else (0,)


def _is_newer(latest_tag: str, current: str) -> bool:
    """判断 latest_tag 是否比 current 新。"""
    a = _parse_version(latest_tag)
    b = _parse_version(current)
    return a > b


@router.get("/update/version")
def get_version() -> dict:
    """
    返回当前应用版本号，供前端展示用。
    仅返回版本字符串，不请求 GitHub。
    """
    return {"version": CURRENT_VERSION}


@router.get("/update/check")
def check_update() -> dict:
    """
    检查是否有新版本。
    请求 GitHub API 获取最新 release，与当前版本比较。
    """
    try:
        r = httpx.get(GITHUB_API_LATEST, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        tag = (data.get("tag_name") or "").strip()
        zip_url = data.get("zipball_url") or ""
        if not tag:
            return {
                "currentVersion": CURRENT_VERSION,
                "latestVersion": None,
                "hasUpdate": False,
                "tagName": None,
                "zipUrl": None,
            }
        has = _is_newer(tag, CURRENT_VERSION)
        return {
            "currentVersion": CURRENT_VERSION,
            "latestVersion": tag,
            "hasUpdate": has,
            "tagName": tag if has else None,
            "zipUrl": zip_url if has else None,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"检查更新失败: {e}")


@router.post("/update/download")
def download_update(body: dict) -> dict:
    """
    将指定 tag 的源码 zip 下载到 data/update/update.zip。
    body: { "tagName": "v0.229" }
    """
    tag_name = (body.get("tagName") or "").strip()
    if not tag_name:
        raise HTTPException(status_code=400, detail="缺少 tagName")
    zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag_name}.zip"
    update_dir = get_update_dir()
    update_dir.mkdir(parents=True, exist_ok=True)
    zip_path = update_dir / "update.zip"
    try:
        with httpx.stream("GET", zip_url, timeout=60.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        return {"ok": True, "path": str(zip_path)}
    except Exception as e:
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=f"下载失败: {e}")


@router.post("/update/run")
def run_update() -> dict:
    """
    触发根目录更新脚本。
    脚本将：关闭前后端与主终端、解压 data/update/update.zip 覆盖、删除 zip、执行 deploy.bat、退出。
    """
    root = get_repo_root()
    backend_pid = os.getpid()
    if sys.platform == "win32":
        script = root / "update.bat"
        if not script.is_file():
            raise HTTPException(status_code=500, detail="根目录未找到 update.bat")
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", "update.bat", str(backend_pid), str(root)],
                cwd=str(root),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"启动更新脚本失败: {e}")
    else:
        script = root / "update.sh"
        if not script.is_file():
            raise HTTPException(status_code=500, detail="根目录未找到 update.sh")
        try:
            subprocess.Popen(
                ["/bin/sh", str(script), str(backend_pid), str(root)],
                cwd=str(root),
                start_new_session=True,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"启动更新脚本失败: {e}")
    return {"ok": True}
