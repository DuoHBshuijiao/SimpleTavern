from __future__ import annotations

from collections import deque
from threading import Lock

_QUEUE_MAX_PER_CHAT = 500
_queues: dict[str, deque[dict[str, str]]] = {}
_lock = Lock()


def enqueue_content_regex_items(chat_id: str, items: list[dict[str, str]]) -> None:
    if not chat_id or not items:
        return
    with _lock:
        q = _queues.setdefault(chat_id, deque())
        for item in items:
            q.append(dict(item))
            while len(q) > _QUEUE_MAX_PER_CHAT:
                q.popleft()


def pop_content_regex_item(chat_id: str) -> dict[str, str] | None:
    if not chat_id:
        return None
    with _lock:
        q = _queues.get(chat_id)
        if not q:
            return None
        item = q.popleft()
        if len(q) == 0:
            _queues.pop(chat_id, None)
        return item


def dequeue_batch(chat_id: str, max_items: int) -> list[dict[str, str]]:
    if not chat_id or max_items <= 0:
        return []
    with _lock:
        q = _queues.get(chat_id)
        if not q:
            return []
        taken: list[dict[str, str]] = []
        for _ in range(min(max_items, len(q))):
            taken.append(dict(q.popleft()))
        if len(q) == 0:
            _queues.pop(chat_id, None)
        return taken


def peek_queue(chat_id: str, max_items: int) -> list[dict[str, str]]:
    """查看队列中最近 N 条提取项（不消费）。"""
    if not chat_id or max_items <= 0:
        return []
    with _lock:
        q = _queues.get(chat_id)
        if not q:
            return []
        start = max(0, len(q) - max_items)
        return [dict(q[i]) for i in range(start, len(q))]


def get_content_regex_queue_size(chat_id: str) -> int:
    if not chat_id:
        return 0
    with _lock:
        q = _queues.get(chat_id)
        return len(q) if q else 0

