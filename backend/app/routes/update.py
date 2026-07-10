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
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.errors import AppError
from app.services.http_log import log_outbound_sync
from app.storage import get_repo_root, get_update_dir, load_update_ignore, save_update_ignore
from app.version import APP_VERSION

router = APIRouter(tags=["update"])

GITHUB_REPO = "DuoHBshuijiao/SimpleTavern"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


class IgnoredTagRequest(BaseModel):
    tag: str


def _current_version_tuple() -> tuple[int, ...]:
    return _parse_version(APP_VERSION)


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


def _fetch_latest_release() -> dict[str, Any]:
    with log_outbound_sync(
        source="update",
        method="GET",
        url=GITHUB_API_LATEST,
        request_headers={"Accept": "application/vnd.github+json"},
    ) as _log:
        r = httpx.get(GITHUB_API_LATEST, timeout=10.0)
        _log.set_response(status=r.status_code, headers=dict(r.headers), text=r.text)
        r.raise_for_status()
        data = r.json()
        _log.set_response(body=data)
        if not isinstance(data, dict):
            raise ValueError("GitHub releases/latest 返回格式异常")
        return data


def _sanitize_release_notes(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _build_update_payload(release: dict[str, Any]) -> dict[str, Any]:
    tag = str(release.get("tag_name") or "").strip()
    zip_url = str(release.get("zipball_url") or "").strip() or None
    release_notes = _sanitize_release_notes(release.get("body"))
    if not tag:
        return {
            "currentVersion": APP_VERSION,
            "latestVersion": None,
            "hasUpdate": False,
            "tagName": None,
            "zipUrl": None,
            "releaseNotes": None,
        }
    has_update = _is_newer(tag, APP_VERSION)
    return {
        "currentVersion": APP_VERSION,
        "latestVersion": tag,
        "hasUpdate": has_update,
        "tagName": tag if has_update else None,
        "zipUrl": zip_url if has_update else None,
        "releaseNotes": release_notes if has_update else None,
    }


def _load_ignored_release_tag() -> str | None:
    raw = load_update_ignore()
    tag = raw.get("ignoredReleaseTag")
    if not isinstance(tag, str):
        return None
    tag = tag.strip()
    if not tag:
        return None
    if _current_version_tuple() >= _parse_version(tag):
        save_update_ignore(None)
        return None
    return tag


@router.get("/update/version")
def get_version() -> dict:
    """
    返回当前应用版本号，供前端展示用。
    仅返回版本字符串，不请求 GitHub。
    """
    return {"version": APP_VERSION}


@router.get("/update/check")
def check_update() -> dict:
    """
    检查是否有新版本。
    请求 GitHub API 获取最新 release，与当前版本比较。
    """
    try:
        return _build_update_payload(_fetch_latest_release())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"检查更新失败: {e}")


@router.get("/update/startup-check")
def startup_check_update() -> dict:
    """启动阶段自动检查更新；会套用 ignoredReleaseTag 计算 shouldNotify。"""
    try:
        payload = _build_update_payload(_fetch_latest_release())
        ignored_tag = _load_ignored_release_tag()
        latest = payload.get("tagName")
        should_notify = bool(payload.get("hasUpdate") and latest and latest != ignored_tag)
        return {
            **payload,
            "ignoredReleaseTag": ignored_tag,
            "shouldNotify": should_notify,
        }
    except AppError:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"启动更新检查失败: {e}")


@router.put("/update/ignored-tag")
def set_ignored_update_tag(body: IgnoredTagRequest) -> dict:
    """保存当前被用户忽略的 release tag。"""
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag 不能为空")
    save_update_ignore(tag)
    return {"ignoredReleaseTag": tag}


@router.delete("/update/ignored-tag")
def clear_ignored_update_tag() -> dict:
    """清空已忽略的 release tag。"""
    save_update_ignore(None)
    return {"ignoredReleaseTag": None}


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
        total_bytes = 0
        with log_outbound_sync(
            source="update",
            method="GET",
            url=zip_url,
            streaming=True,
        ) as _log:
            with httpx.stream("GET", zip_url, timeout=60.0, follow_redirects=True) as resp:
                _log.set_response(status=resp.status_code, headers=dict(resp.headers))
                resp.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        total_bytes += len(chunk)
            _log.set_response(body={"_downloaded": True, "bytes": total_bytes, "path": str(zip_path)})
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
