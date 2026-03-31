"""AI workspace path resolution for assistant tools."""

from __future__ import annotations

from pathlib import Path

from app.storage import ai_workspace_dir


def resolve_ai_path(path_str: str) -> Path:
    if not path_str or path_str.strip() == "":
        raise ValueError("path is required")
    raw = Path(path_str)
    if raw.is_absolute():
        raise ValueError("absolute path is not allowed")
    base = ai_workspace_dir().resolve()
    target = (base / raw).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("path must be under ai_workspace") from exc
    return target
