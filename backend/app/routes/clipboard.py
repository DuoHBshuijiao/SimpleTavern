"""Extract pasted text from client-supplied clipboard HTML."""

from __future__ import annotations

from html.parser import HTMLParser

from fastapi import APIRouter
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


@router.post("/resolve-rich-paste", response_model=ResolveRichPasteResponse)
def resolve_rich_paste(req: ResolveRichPasteRequest) -> ResolveRichPasteResponse:
    """Return only text and never open paths named in pasted HTML."""
    text = (req.text or "").strip()
    if not text and req.html:
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

    return ResolveRichPasteResponse(text=text)
