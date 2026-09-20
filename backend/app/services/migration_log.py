"""迁移警告（T-813）：结构转换必须可见，禁止静默修复损坏配置。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.errors import redact_sensitive_text
from app.storage import append_jsonl_object, get_data_dir


def migration_warnings_path():
    return get_data_dir() / "migration_warnings.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def write_migration_warning(
    *,
    code: str,
    message: str,
    path: str | None = None,
    detail: str | None = None,
) -> None:
    payload = {
        "ts": _now_iso(),
        "code": code,
        "message": redact_sensitive_text(message),
        "path": path,
        "detail": redact_sensitive_text(detail) if detail else None,
    }
    try:
        append_jsonl_object(migration_warnings_path(), payload)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("failed to write migration warning")


def iter_migration_warnings(limit: int = 50) -> list[dict[str, Any]]:
    path = migration_warnings_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    import json

                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        return []
    if limit <= 0:
        return rows
    return rows[-limit:]


def migration_warning_count() -> int:
    path = migration_warnings_path()
    if not path.exists():
        return 0
    try:
        count = 0
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                if raw.strip():
                    count += 1
        return count
    except OSError:
        return 0
