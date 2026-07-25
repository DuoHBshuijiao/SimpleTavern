"""Shared worker/scanner health state for MVU and content-regex background jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.errors import AppError


WorkerStatus = Literal["ok", "degraded", "paused", "disabled", "error"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


@dataclass
class WorkerHealth:
    status: WorkerStatus = "ok"
    enabled: bool = True
    failure_count: int = 0
    paused: bool = False
    last_error: dict[str, Any] | None = None
    enable_error: dict[str, Any] | None = None
    next_retry_at: str | None = None
    last_success_at: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def record_success(self) -> None:
        self.failure_count = 0
        self.paused = False
        self.last_error = None
        self.next_retry_at = None
        self.last_success_at = _now_iso()
        self.status = "ok" if self.enabled else "disabled"

    def record_failure(
        self,
        error: AppError,
        *,
        pause_after: int = 5,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.failure_count += 1
        self.last_error = error.to_dict()
        if retry_after_seconds is not None and retry_after_seconds > 0:
            retry_at = datetime.now(timezone.utc).timestamp() + retry_after_seconds
            self.next_retry_at = datetime.fromtimestamp(retry_at, tz=timezone.utc).astimezone().isoformat()
        else:
            self.next_retry_at = None
        if self.failure_count >= pause_after:
            self.paused = True
            self.status = "paused"
        else:
            self.status = "degraded"

    def set_enable_error(self, error: AppError | None) -> None:
        if error is None:
            self.enable_error = None
            return
        self.enable_error = error.to_dict()
        self.enabled = False
        self.status = "error"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "enabled": self.enabled,
            "failureCount": self.failure_count,
            "paused": self.paused,
            "lastError": self.last_error,
            "enableError": self.enable_error,
            "nextRetryAt": self.next_retry_at,
            "lastSuccessAt": self.last_success_at,
        }
        payload.update(self.extras)
        return payload
