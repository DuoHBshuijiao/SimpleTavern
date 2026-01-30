"""
字体管理路由模块

提供字体文件的列表、上传和获取 API。字体保存在 data/fonts，不随备份导出。

主要功能：
    - GET /fonts: 列出已导入的字体文件名
    - POST /fonts: 上传字体文件
    - GET /fonts/{filename}: 获取字体文件（用于 @font-face）
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.storage import font_path, fonts_dir, save_font

router = APIRouter(tags=["fonts"])

ALLOWED_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2"}
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def _is_allowed_font(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_EXTENSIONS and SAFE_FILENAME_RE.match(path.name)


@router.get("/fonts")
def list_fonts() -> list[str]:
    """
    列出 data/fonts 下所有字体文件名（仅允许的扩展名）。
    """
    directory = fonts_dir()
    if not directory.exists():
        return []
    names = [p.name for p in directory.iterdir() if p.is_file() and _is_allowed_font(p)]
    return sorted(names)


@router.get("/fonts/{filename}")
def get_font(filename: str) -> FileResponse:
    """
    返回字体文件，用于前端 @font-face url()。
    """
    path = Path(filename)
    if not _is_allowed_font(path):
        raise HTTPException(status_code=400, detail="invalid font filename")
    full = font_path(path.name)
    if not full.exists():
        raise HTTPException(status_code=404, detail="font not found")
    return FileResponse(full, media_type="application/octet-stream")


@router.post("/fonts")
async def upload_font(file: UploadFile = File(...)) -> dict:
    """
    上传字体文件到 data/fonts。导入后实时替换为当前选中字体，不随备份导出。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    path = Path(file.filename)
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported font type, allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    if not SAFE_FILENAME_RE.match(path.name):
        raise HTTPException(status_code=400, detail="invalid filename")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    save_font(path.name, data)
    return {"filename": path.name}
