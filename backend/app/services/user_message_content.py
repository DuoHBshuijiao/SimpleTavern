from __future__ import annotations

import base64
from typing import Any

ATTACHMENT_SECTION_START = "--- 附件: {name} ---"
ATTACHMENT_SECTION_END = "--- 结束 ---"



def _build_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"



def merge_user_message_text(
    base_text: str,
    text_attachments: list[tuple[str, str]] | None = None,
) -> str:
    parts: list[str] = []
    text = (base_text or "").strip()
    if text:
        parts.append(text)
    for name, content in text_attachments or []:
        attachment_text = (content or "").strip()
        if not attachment_text:
            continue
        parts.append(ATTACHMENT_SECTION_START.format(name=name or "未命名附件"))
        parts.append(attachment_text)
        parts.append(ATTACHMENT_SECTION_END)
    return "\n\n".join(parts).strip()



def build_user_message_content(
    base_text: str,
    *,
    text_attachments: list[tuple[str, str]] | None = None,
    image_items: list[tuple[bytes, str]] | None = None,
    image_fallback_mode: bool = False,
) -> str | list[dict[str, Any]]:
    merged_text = merge_user_message_text(base_text, text_attachments)
    images = image_items or []
    if not images:
        return merged_text
    if image_fallback_mode:
        suffix = "\n".join("[image]" for _ in images)
        if merged_text and suffix:
            return f"{merged_text}\n{suffix}".strip()
        return (merged_text or suffix).strip()
    parts: list[dict[str, Any]] = []
    if merged_text:
        parts.append({"type": "text", "text": merged_text})
    for image_bytes, mime_type in images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": _build_data_url(image_bytes, mime_type or "image/png")},
            }
        )
    if not parts:
        return ""
    return parts
