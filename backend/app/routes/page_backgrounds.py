"""
页面背景图管理路由模块

提供页面背景图文件的上传、获取与删除 API。背景图保存在 data/page_backgrounds，不随备份导出。
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from app.storage import delete_page_background, page_background_path, save_page_background


router = APIRouter(tags=["page-backgrounds"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def _validated_page_background_name(filename: str) -> Path:
    path = Path(filename)
    if not filename or path.name != filename:
        raise HTTPException(status_code=400, detail="invalid page background filename")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS or not SAFE_FILENAME_RE.match(path.name):
        raise HTTPException(status_code=400, detail="invalid page background filename")
    return path


def _page_background_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


@router.get("/page-backgrounds/{filename}")
def get_page_background(filename: str) -> FileResponse:
    """
    返回页面背景图文件。
    """
    path = _validated_page_background_name(filename)
    full = page_background_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="page background not found")
    return FileResponse(full, media_type=_page_background_media_type(full))


@router.post("/page-backgrounds")
async def upload_page_background(file: UploadFile = File(...)) -> dict[str, str]:
    """
    上传页面背景图到 data/page_backgrounds，并返回生成后的安全文件名。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    source = Path(file.filename)
    suffix = source.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image type, allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    filename = f"{uuid4().hex}{suffix}"
    save_page_background(filename, data)
    return {"filename": filename}


@router.delete("/page-backgrounds/{filename}", status_code=204)
def remove_page_background(filename: str) -> Response:
    """
    删除页面背景图文件。
    """
    path = _validated_page_background_name(filename)
    full = page_background_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="page background not found")
    delete_page_background(path.name)
    return Response(status_code=204)