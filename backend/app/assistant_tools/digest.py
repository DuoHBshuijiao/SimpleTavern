"""Stable short digest of tool arguments for logs and tool records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def args_digest(args: dict[str, Any]) -> str:
    try:
        raw = json.dumps(args, sort_keys=True, ensure_ascii=False)
    except Exception:
        raw = str(args)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
