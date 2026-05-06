"""MVU 守护进程 — per-chat worker 生命周期 + 双触发器 + 互斥锁 + 冷却。

触发器：
  1. generate done  → signal_generate_done(chat_id)  立即唤醒
  2. 队列堆积      → daemon 每 5s 轮询检查

共用同一互斥锁，5 秒冷却防止高频重复触发。signal_queue_threshold 保留
供未来扩展，当前由轮询覆盖。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

logger = logging.getLogger(__name__)

from app.content_regex_queue import clear_queue, dequeue_by_message_id, get_content_regex_queue_size
from app.mvu_model_resolve import resolve_mvu_model_from_settings
from app.mvu_system_prompt import load_mvu_system_prompt
from app.schemas import (
    AssistantSettings,
    CharacterCard,
    Chat,
    MvuWorkLogEntry,
    build_reasoning_request_config,
    filter_reasoning_extra_body_for_upstream,
)
from app.services.mvu_agent import MvuAgentEvent, MvuAgentJob, MvuAgentRunContext, MvuAgentService
from app.storage import (
    load_chat,
    load_character,
    load_mvu_logs,
    load_settings,
    save_chat,
    save_mvu_logs,
)

_COOLDOWN_SECS = 5.0

# per-chat 原语
_events: dict[str, asyncio.Event] = {}
_locks: dict[str, asyncio.Lock] = {}
_tasks: dict[str, asyncio.Task] = {}
_last_run: dict[str, float] = {}
_context_window_counts: dict[str, int] = {}

# SSE 订阅者（per chat_id 的 asyncio.Queue 列表）
_subscribers: dict[str, list[asyncio.Queue]] = {}
_QUEUE_MAX = 200


def subscribe(chat_id: str) -> asyncio.Queue:
    """为 SSE 路由创建一个订阅队列。返回 asyncio.Queue，容量 200。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(chat_id, []).append(q)
    return q


def unsubscribe(chat_id: str, q: asyncio.Queue) -> None:
    """取消 SSE 订阅。"""
    subs = _subscribers.get(chat_id)
    if subs:
        try:
            subs.remove(q)
        except ValueError:
            pass


async def _broadcast(chat_id: str, event: MvuAgentEvent) -> None:
    """将事件推送到所有 SSE 订阅者。"""
    subs = _subscribers.get(chat_id, [])
    for q in subs:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _get_or_create(chat_id: str) -> tuple[asyncio.Event, asyncio.Lock]:
    if chat_id not in _events:
        _events[chat_id] = asyncio.Event()
        _locks[chat_id] = asyncio.Lock()
        _last_run[chat_id] = 0.0
    return _events[chat_id], _locks[chat_id]


def _resolve_mvu_runtime_config(chat: Chat, character: CharacterCard | None) -> tuple[Literal["regex", "directive"], str | None]:
    overrides = getattr(chat, "overrides", None)
    mode = getattr(overrides, "mvuMode", None) if overrides is not None else None
    if mode not in ("regex", "directive"):
        mode = getattr(character, "mvuMode", None) if character is not None else None
    if mode not in ("regex", "directive"):
        mode = "regex"

    directive = getattr(overrides, "mvuDirective", None) if overrides is not None else None
    if directive is None or not str(directive).strip():
        directive = getattr(character, "mvuDirective", None) if character is not None else None
    directive = str(directive).strip() if directive is not None else ""
    return mode, directive or None


def _next_context_window_count(chat_id: str) -> int:
    current = _context_window_counts.get(chat_id, 10)
    if current >= 30:
        _context_window_counts[chat_id] = 10
    else:
        _context_window_counts[chat_id] = min(current + 2, 30)
    return current


def ensure_mvu_worker(chat_id: str) -> bool:
    """确保 chat_id 的 MVU worker loop 已启动。返回 True 表示已在运行或成功启动。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        return False
    try:
        character = load_character(chat.characterId)
    except FileNotFoundError:
        return False
    if not getattr(character, "mvuEnabled", False):
        return False

    _get_or_create(chat_id)

    existing = _tasks.get(chat_id)
    if existing is not None and not existing.done():
        return True

    # 首次启动 worker：入口清理——清空队列残留，scanner 下轮按规则正确入队
    clear_queue(chat_id)

    _tasks[chat_id] = asyncio.create_task(_mvu_loop(chat_id))
    return True


async def _mvu_loop(chat_id: str) -> None:
    event, lock = _events[chat_id], _locks[chat_id]

    while True:
        triggered_by_signal = False
        try:
            await asyncio.wait_for(event.wait(), timeout=5)
            triggered_by_signal = True
        except asyncio.TimeoutError:
            pass
        event.clear()

        async with lock:
            now = time.monotonic()
            if now - _last_run.get(chat_id, 0) < _COOLDOWN_SECS:
                continue

            try:
                chat = load_chat(chat_id)
                character = load_character(chat.characterId)
            except FileNotFoundError:
                continue
            mode, _directive = _resolve_mvu_runtime_config(chat, character)

            queue_size = get_content_regex_queue_size(chat_id)
            if mode == "directive":
                if not triggered_by_signal:
                    continue
            elif queue_size == 0:
                continue

            try:
                await _run_once(chat_id)
            except Exception:
                continue

            _last_run[chat_id] = time.monotonic()


async def _run_once(chat_id: str) -> None:
    """执行一次完整的 MVU job：组装 job → 运行 agent → 持久化日志 → 消费队列。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        return
    try:
        character = load_character(chat.characterId)
    except FileNotFoundError:
        character = None

    mode, directive = _resolve_mvu_runtime_config(chat, character)

    settings = load_settings()

    # 解析 API 端点：优先使用会话 preset，否则全局设置
    preset_id = getattr(chat.overrides, "presetId", None)
    base_url = settings.llm.baseUrl
    api_key = settings.llm.apiKey

    found_preset = None
    if preset_id:
        found_preset = next((p for p in settings.apiPresets if p.id == preset_id), None)
        if found_preset:
            base_url = found_preset.baseUrl
            api_key = found_preset.apiKey

    # 模型名称多级回退：
    #   1) 全局 settings.mvuModel → defaultModel → modelCandidates（见 mvu_model_resolve）
    #   2) 当前会话 preset 的首个可用模型
    model = resolve_mvu_model_from_settings(settings)
    if not model and found_preset and found_preset.models:
        model = (found_preset.models[0] or "").strip()

    if not model:
        logger.error("chat %s: MVU model is empty after all resolution attempts, skipping run", chat_id)
        await _broadcast(chat_id, MvuAgentEvent("error", {
            "message": "MVU 模型未配置，请在全局设置中指定 MVU 模型或默认模型",
        }))
        return

    reasoning_cfg = build_reasoning_request_config(settings)
    extra_body = filter_reasoning_extra_body_for_upstream(model, reasoning_cfg["extra_body"])
    tool_temperature: float | None = None
    if not reasoning_cfg["thinking_enabled"]:
        tool_temperature = settings.generationDefaults.temperature

    # 正则模式消费队列；指令模式由生成完成信号触发，不读取/消费正则队列。
    consumed_msg_id: str | None = None
    if mode == "regex":
        consumed_msg_id, queue_items = dequeue_by_message_id(chat_id)
        if not queue_items:
            return
        context_window_count = 10
    else:
        queue_items = []
        context_window_count = _next_context_window_count(chat_id)

    # 组装 job
    from app.assistant_tools.handlers.mvu import render_tables_markdown

    state = chat.stateVariables
    tables = list(state.tables) if state else []
    state_md = render_tables_markdown(tables)

    queue_text = "\n".join(
        f"- [{it.get('ruleName', '')}] {it.get('value', '')} (action={it.get('action', '')})"
        for it in queue_items
    ) if queue_items else "（队列为空）"

    recent = chat.messages[-context_window_count:] if len(chat.messages) > context_window_count else chat.messages
    ctx_lines: list[str] = []
    for m in recent:
        content = (m.content or "").strip()
        if not content:
            continue
        label = "用户" if m.role == "user" else ("角色" if m.role == "assistant" else m.role)
        ctx_lines.append(f"[{label}]: {content}")
    context_md = "\n\n".join(ctx_lines) if ctx_lines else "（暂无对话）"

    job = MvuAgentJob(
        chat_id=chat_id,
        character_id=chat.characterId,
        system_prompt=load_mvu_system_prompt(),
        state=state,
        state_markdown=state_md,
        queue_items=queue_items,
        queue_text=queue_text,
        context_markdown=context_md,
        mode=mode,
        directive=directive,
        context_window_count=context_window_count,
    )

    run_ctx = MvuAgentRunContext(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=tool_temperature,
        extra_body=extra_body,
    )

    agent = MvuAgentService(run_ctx)
    events, log_entries = await agent.run_job(
        job,
        on_event=lambda evt: _broadcast(chat_id, evt),
    )

    # 推送遗留事件到 SSE 订阅者（安全网：防 _push 中的 ensure_future 未覆盖的路径）
    for event in events:
        await _broadcast(chat_id, event)

    # 持久化工作日志
    if log_entries:
        existing = load_mvu_logs(chat.characterId, chat_id)
        save_mvu_logs(chat.characterId, chat_id, existing + log_entries)

    # 标记已消费消息：最新被处理消息设 mvuProcessed，清除旧标记
    if mode == "regex" and consumed_msg_id:
        try:
            chat_reload = load_chat(chat_id)
        except FileNotFoundError:
            return
        dirty = False
        for m in chat_reload.messages:
            if m.id == consumed_msg_id:
                if not m.mvuProcessed:
                    m.mvuProcessed = True
                    dirty = True
            elif m.mvuProcessed:
                m.mvuProcessed = False
                dirty = True
        if dirty:
            save_chat(chat_reload)


def signal_generate_done(chat_id: str) -> None:
    """generate.py SSE [DONE] 后调用，唤醒 MVU worker 处理队列。"""
    evt = _events.get(chat_id)
    if evt is not None:
        evt.set()


def signal_queue_threshold(chat_id: str) -> None:
    """content_regex enqueue 后若队列≥3 则唤醒 MVU worker。"""
    evt = _events.get(chat_id)
    if evt is not None:
        evt.set()
