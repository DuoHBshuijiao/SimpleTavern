"""
剪贴板富文本解析路由

供前端粘贴时调用：解析 text/html 中的 file:// 图片路径（如 QQ 等桌面程序写入的），
在服务端读取本地图片并返回 base64，使浏览器无法直接读取的 file:// 也能在输入框草稿中显示。

仅允许读取系统临时目录下的文件，避免任意文件读取。
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/clipboard", tags=["clipboard"])


class ResolveRichPasteRequest(BaseModel):
    text: str = Field(default="", description="粘贴的纯文本")
    html: str = Field(default="", description="粘贴的 HTML（可能含 file:// 图片）")


class ResolvedImage(BaseModel):
    base64: str = Field(..., description="图片 base64 数据（不含 data:xxx 前缀）")
    mimeType: str = Field(..., description="MIME 类型，如 image/png")
    name: str = Field(..., description="建议文件名，用于前端展示")


class ResolveRichPasteResponse(BaseModel):
    text: str = Field(..., description="使用的文本（与请求 text 一致，或从 HTML 抽取）")
    images: list[ResolvedImage] = Field(default_factory=list, description="解析出的图片列表")


# 仅允许读取的根目录：系统临时目录（QQ 等常把复制图片放这里）
_ALLOWED_ROOT = Path(tempfile.gettempdir()).resolve()


def _file_url_to_path(file_url: str) -> Path | None:
    """将 file:///C:/... 或 file:///C:\... 转为 Path，非法或非 file 协议返回 None。"""
    try:
        parsed = urlparse(file_url)
        if parsed.scheme != "file":
            return None
        path_str = unquote(parsed.path)
        if not path_str:
            return None
        # Windows: path 可能为 /C:/Users/... 或 /C:\Users\...
        if path_str.startswith("/") and len(path_str) > 2 and path_str[2] in (":", "/"):
            path_str = path_str[1:]
        path_str = path_str.replace("/", "\\") if "\\" in path_str or path_str[1:2] == ":" else path_str
        return Path(path_str).resolve()
    except Exception:
        return None


def _is_path_allowed(path: Path) -> bool:
    """路径必须在允许的根目录下。"""
    try:
        resolved = path.resolve()
        return resolved.is_file() and str(resolved).startswith(str(_ALLOWED_ROOT))
    except Exception:
        return False


def _mime_from_path(path: Path) -> str:
    """根据文件头或扩展名返回 MIME。"""
    with open(path, "rb") as f:
        raw = f.read(64)
    kind = _detect_image_kind(raw)
    if kind == "jpeg":
        return "image/jpeg"
    if kind == "png":
        return "image/png"
    if kind == "gif":
        return "image/gif"
    if kind == "webp":
        return "image/webp"
    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"
    return "image/png"


def _detect_image_kind(raw: bytes) -> str | None:
    """
    使用文件头魔数检测常见图片类型。
    替代 Python 3.13 移除的 imghdr，保持纯标准库实现。
    """
    if len(raw) >= 8 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(raw) >= 3 and raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(raw) >= 6 and (raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a")):
        return "gif"
    if len(raw) >= 12 and raw[0:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return None


def _extract_file_urls_from_html(html: str) -> list[str]:
    """从 HTML 中提取所有 <img src="file://..."> 的 URL。"""
    pattern = re.compile(r'<img[^>]+src\s*=\s*["\'](file://[^"\']+)["\']', re.I)
    return list(dict.fromkeys(pattern.findall(html)))  # 去重保序


@router.post("/resolve-rich-paste", response_model=ResolveRichPasteResponse)
def resolve_rich_paste(req: ResolveRichPasteRequest) -> ResolveRichPasteResponse:
    """
    解析富文本粘贴内容：从 HTML 中提取 file:// 图片路径，在服务端读取并返回 base64。
    仅允许读取系统临时目录下的文件。
    """
    text = (req.text or "").strip()
    if not text and req.html:
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text: list[str] = []

            def handle_data(self, data: str) -> None:
                self.text.append(data)

        parser = TextExtractor()
        try:
            parser.feed(req.html)
            text = "".join(parser.text).strip()
        except Exception:
            pass

    images: list[ResolvedImage] = []
    if not req.html:
        return ResolveRichPasteResponse(text=text, images=images)

    for file_url in _extract_file_urls_from_html(req.html):
        path = _file_url_to_path(file_url)
        if not path or not _is_path_allowed(path):
            continue
        try:
            data = path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            mime = _mime_from_path(path)
            name = path.name or "pasted.png"
        except Exception:
            continue
        images.append(ResolvedImage(base64=b64, mimeType=mime, name=name))

    return ResolveRichPasteResponse(text=text, images=images)
