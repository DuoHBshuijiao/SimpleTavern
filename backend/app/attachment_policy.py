from __future__ import annotations

from pathlib import Path

ASSISTANT_TEXT_ATTACHMENT_MAX_BYTES = 2 * 1024 * 1024
ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES = 100 * 1024 * 1024

MAIN_CHAT_IMAGES_ONLY = True

_ASSISTANT_TEXT_EXTENSIONS = {".txt", ".json", ".jsonl", ".xml"}
_ASSISTANT_TEXT_MIME_TYPES = {
    "text/plain",
    "text/json",
    "text/xml",
    "application/json",
    "application/xml",
}
_ASSISTANT_IMAGE_MIME_PREFIX = "image/"


def normalize_mime_type(mime_type: str | None) -> str:
    return (mime_type or "").split(";", 1)[0].strip().lower()


def is_image_mime_type(mime_type: str | None) -> bool:
    return normalize_mime_type(mime_type).startswith(_ASSISTANT_IMAGE_MIME_PREFIX)



def is_assistant_text_attachment(mime_type: str | None, filename: str | None = None) -> bool:
    normalized_mime = normalize_mime_type(mime_type)
    suffix = Path(filename or "").suffix.lower()
    if suffix in _ASSISTANT_TEXT_EXTENSIONS:
        return True
    if normalized_mime in _ASSISTANT_TEXT_MIME_TYPES:
        return True
    if normalized_mime.startswith("text/"):
        return True
    if normalized_mime.endswith("+json") or normalized_mime.endswith("+xml"):
        return True
    return False



def assistant_attachment_kind(mime_type: str | None, filename: str | None = None) -> str | None:
    if is_image_mime_type(mime_type):
        return "image"
    if is_assistant_text_attachment(mime_type, filename):
        return "text"
    return None
