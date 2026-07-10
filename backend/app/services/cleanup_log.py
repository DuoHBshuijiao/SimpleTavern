from __future__ import annotations

import logging
from pathlib import Path

from app.errors import redact_sensitive_text
from app.request_context import get_request_id


logger = logging.getLogger(__name__)


def log_cleanup_failure(
    *,
    source: str,
    exc: BaseException,
    path: Path | str | None = None,
    task_id: str | None = None,
) -> None:
    """记录不应覆盖主操作结果的清理失败。"""
    logger.warning(
        "cleanup_failed source=%s requestId=%s taskId=%s path=%s error=%s",
        source,
        get_request_id(),
        task_id,
        str(path) if path is not None else None,
        redact_sensitive_text(exc),
    )
