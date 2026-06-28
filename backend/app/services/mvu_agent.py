"""MVU agent loop service — event-driven, non-interactive background worker.

与 AssistantAgentService（交互式、用户消息驱动）职责隔离：
- MVU agent 由系统事件触发（生成完成 / 队列堆积），无用户消息
- 非流式 LLM 调用（后台无观众），仅产出 work log entry 事件
- 工具集限定为 MVU 域与正文正则 CRUD 工具，不含 workspace/chat/worldbook
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.executor import execute_tool
from app.assistant_tools.registry import registered_tools
from app.assistant_tools import result as tool_result
from app.llm.openai_compat import chat_completions_message
from app.kg_inject import mvu_tool_names
from app.schemas import AssistantSettings, MvuWorkLogEntry, StateVariables


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _build_mvu_tools(*, include_knowledge_graph: bool = True) -> list[dict[str, Any]]:
    allowed = mvu_tool_names(include_knowledge_graph)
    tools: list[dict[str, Any]] = []
    for rt in registered_tools():
        if rt.name in allowed:
            tools.append({
                "type": "function",
                "function": {
                    "name": rt.name,
                    "description": rt.description,
                    "parameters": rt.parameters,
                },
            })
    return tools


def _normalize_tool_calls_ids(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tool_calls:
        return []
    out: list[dict[str, Any]] = []
    for index, tc in enumerate(tool_calls):
        normalized = dict(tc)
        if not str(normalized.get("id") or "").strip():
            fn_name = str((normalized.get("function") or {}).get("name") or "tool")
            normalized["id"] = f"call_mvu_{index}_{fn_name}"
        out.append(normalized)
    return out


@dataclass(frozen=True)
class MvuAgentJob:
    """MVU agent 单次运行的输入，由 daemon 组装。"""
    chat_id: str
    character_id: str
    system_prompt: str
    state: StateVariables | None
    state_markdown: str
    queue_items: list[dict[str, str]]
    queue_text: str
    context_markdown: str
    mode: Literal["regex", "directive"] = "regex"
    directive: str | None = None
    context_window_count: int = 10
    knowledge_graph_enabled: bool = True


@dataclass(frozen=True)
class MvuAgentEvent:
    """MVU agent 输出事件（供 SSE 推送与日志持久化）。"""
    kind: Literal["log_entry", "done", "error"]
    data: dict[str, Any]


@dataclass(frozen=True)
class MvuAgentRunContext:
    """MVU agent 运行参数。"""
    base_url: str
    api_key: str
    model: str
    temperature: float | None = None
    max_tool_turns: int = 5
    extra_body: dict[str, Any] | None = None


class MvuAgentService:
    """MVU agent 循环 — 非交互、非流式、仅产出 log_entry 事件。"""

    def __init__(self, run_ctx: MvuAgentRunContext, *, include_knowledge_graph: bool = True):
        self._ctx = run_ctx
        self._tools = _build_mvu_tools(include_knowledge_graph=include_knowledge_graph)

    def _tool_ctx(self, chat_id: str) -> AssistantToolContext:
        return AssistantToolContext(
            chat_id=chat_id,
            scope="mvu",
            allow_write_memory=False,
            allow_destructive_tools=False,
            allow_web_search=False,
            assistant_settings=AssistantSettings(),
        )

    async def run_job(
        self,
        job: MvuAgentJob,
        *,
        on_event: Callable[[MvuAgentEvent], Awaitable[None]] | None = None,
    ) -> tuple[list[MvuAgentEvent], list[MvuWorkLogEntry]]:
        """运行一个 MVU job。

        on_event: 可选异步回调，每次产生事件时立即触发（用于实时 SSE 推送）。

        Returns:
            (events, log_entries): events 供 SSE 推送，log_entries 供持久化到 mvu_logs.json。
        """
        events: list[MvuAgentEvent] = []
        log_entries: list[MvuWorkLogEntry] = []

        async def _push(evt: MvuAgentEvent) -> None:
            events.append(evt)
            if on_event:
                await on_event(evt)

        async def _alog(event_type: str, summary: str, detail: dict[str, Any] | None = None) -> MvuWorkLogEntry:
            entry = MvuWorkLogEntry(
                id=uuid4().hex,
                chatId=job.chat_id,
                timestamp=_now_iso(),
                eventType=event_type,
                summary=summary,
                detail=detail,
            )
            log_entries.append(entry)
            await _push(MvuAgentEvent("log_entry", entry.model_dump(mode="json")))
            return entry

        if job.mode == "directive":
            await _alog("triggered", "指令模式：根据生成完成信号维护状态", {
                "mode": job.mode,
                "contextWindowCount": job.context_window_count,
            })
        else:
            await _alog("triggered", f"队列 {len(job.queue_items)} 条待消费", {
                "mode": job.mode,
                "queueConsumed": len(job.queue_items),
            })

        tool_ctx = self._tool_ctx(job.chat_id)

        if job.mode == "directive":
            directive = (job.directive or "").strip() or "（未配置指令；仅根据最近对话中明确的数据变化维护状态）"
            context_block = (
                "## 模式\n"
                "directive：无正则队列，依据数据变更指令和最近对话维护状态。\n\n"
                f"## 数据变更指令\n{directive}\n\n"
                f"## 当前状态\n{job.state_markdown}\n\n"
                f"## 最近 {job.context_window_count} 条对话\n{job.context_markdown}"
            )
        else:
            context_block = (
                f"## 模式\nregex：根据提取队列维护状态。\n\n"
                f"## 当前状态\n{job.state_markdown}\n\n"
                f"## 提取队列\n{job.queue_text}\n\n"
                f"## 最近对话\n{job.context_markdown}"
            )
        current_messages: list[dict[str, Any]] = [
            {"role": "system", "content": job.system_prompt},
            {"role": "user", "content": f"请根据以下上下文维护状态变量：\n\n{context_block}"},
        ]

        try:
            for turn in range(self._ctx.max_tool_turns):
                resp = await chat_completions_message(
                    base_url=self._ctx.base_url,
                    api_key=self._ctx.api_key,
                    model=self._ctx.model,
                    messages=current_messages,
                    temperature=self._ctx.temperature,
                    tools=self._tools,
                    extra_body=self._ctx.extra_body if self._ctx.extra_body else None,
                )

                tool_calls = _normalize_tool_calls_ids(resp.tool_calls)

                assistant_msg: dict[str, Any] = {
                    "role": resp.role or "assistant",
                    "content": resp.content or "",
                }
                if resp.reasoning_content:
                    assistant_msg["reasoning_content"] = resp.reasoning_content
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                current_messages.append(assistant_msg)

                if not tool_calls:
                    await _alog("commit", "任务完成，Agent 无更多工具调用")
                    done_evt = MvuAgentEvent("done", {
                        "ok": True,
                        "chatId": job.chat_id,
                        "mode": job.mode,
                        "queueConsumed": len(job.queue_items),
                    })
                    events.append(done_evt)
                    if on_event:
                        await on_event(done_evt)
                    return events, log_entries

                for tc in tool_calls:
                    fn_name = str((tc.get("function") or {}).get("name") or "")
                    raw_args = str((tc.get("function") or {}).get("arguments") or "{}")
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}

                    outcome = execute_tool(fn_name, args, tool_ctx)
                    result = outcome.result

                    tool_msg: dict[str, Any] = {
                        "role": "tool",
                        "tool_call_id": str(tc.get("id") or ""),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    current_messages.append(tool_msg)

                    ok = bool(result.get("ok"))
                    code = result.get("code", "")
                    summary = (
                        f"{fn_name}: {'OK' if ok else code} — "
                        f"{str(result.get('message', '') or list(result.get('data', {}).keys()))[:120]}"
                    )
                    await _alog("tool_call" if ok else "error", summary, {
                        "tool": fn_name,
                        "args": args,
                        "ok": ok,
                    })

            await _alog("error", f"达到工具调用轮次上限 max_tool_turns={self._ctx.max_tool_turns}")
            limit_evt = MvuAgentEvent("error", {
                "message": f"tool call loop limit exceeded: max_tool_turns={self._ctx.max_tool_turns}",
                "code": tool_result.LIMIT_EXCEEDED,
            })
            events.append(limit_evt)
            if on_event:
                await on_event(limit_evt)
            return events, log_entries

        except Exception as exc:
            await _alog("error", f"异常: {exc}")
            err_evt = MvuAgentEvent("error", {"message": str(exc)})
            events.append(err_evt)
            if on_event:
                await on_event(err_evt)
            return events, log_entries
