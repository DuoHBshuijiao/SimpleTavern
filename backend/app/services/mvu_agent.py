"""MVU agent loop service — event-driven, non-interactive background worker.

与 AssistantAgentService（交互式、用户消息驱动）职责隔离：
- MVU agent 由系统事件触发（生成完成 / 队列堆积），无用户消息
- 非流式 LLM 调用（后台无观众），仅产出 work log entry 事件
- 工具集限定为 5 个 MVU 域工具，不含 workspace/chat/worldbook
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.executor import execute_tool
from app.assistant_tools.registry import registered_tools
from app.assistant_tools import result as tool_result
from app.llm.openai_compat import chat_completions_message
from app.schemas import AssistantSettings, MvuWorkLogEntry, StateVariables

_MVU_TOOL_NAMES = {
    "mvu_get_session_state",
    "mvu_define_table",
    "mvu_set_cell",
    "mvu_get_chat_context",
    "read_mvu_logs",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _build_mvu_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for rt in registered_tools():
        if rt.name in _MVU_TOOL_NAMES:
            tools.append({
                "type": "function",
                "function": {
                    "name": rt.name,
                    "description": rt.description,
                    "parameters": rt.parameters,
                },
            })
    return tools


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

    def __init__(self, run_ctx: MvuAgentRunContext):
        self._ctx = run_ctx
        self._tools = _build_mvu_tools()

    def _tool_ctx(self, chat_id: str) -> AssistantToolContext:
        return AssistantToolContext(
            chat_id=chat_id,
            scope="mvu",
            allow_write_memory=False,
            allow_destructive_tools=False,
            assistant_settings=AssistantSettings(),
        )

    async def run_job(self, job: MvuAgentJob) -> tuple[list[MvuAgentEvent], list[MvuWorkLogEntry]]:
        """运行一个 MVU job。

        Returns:
            (events, log_entries): events 供 SSE 推送，log_entries 供持久化到 mvu_logs.json。
        """
        events: list[MvuAgentEvent] = []
        log_entries: list[MvuWorkLogEntry] = []

        def _log(event_type: str, summary: str, detail: dict[str, Any] | None = None) -> MvuWorkLogEntry:
            entry = MvuWorkLogEntry(
                id=uuid4().hex,
                chatId=job.chat_id,
                timestamp=_now_iso(),
                eventType=event_type,
                summary=summary,
                detail=detail,
            )
            log_entries.append(entry)
            events.append(MvuAgentEvent("log_entry", entry.model_dump(mode="json")))
            return entry

        _log("triggered", f"队列 {len(job.queue_items)} 条待消费")

        tool_ctx = self._tool_ctx(job.chat_id)

        context_block = (
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

                tool_calls = resp.tool_calls

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
                    _log("commit", "任务完成，Agent 无更多工具调用")
                    events.append(MvuAgentEvent("done", {
                        "ok": True,
                        "chatId": job.chat_id,
                        "queueConsumed": len(job.queue_items),
                    }))
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
                    _log("tool_call" if ok else "error", summary, {
                        "tool": fn_name,
                        "args": args,
                        "ok": ok,
                    })

            _log("error", f"达到工具调用轮次上限 max_tool_turns={self._ctx.max_tool_turns}")
            events.append(MvuAgentEvent("error", {
                "message": f"tool call loop limit exceeded: max_tool_turns={self._ctx.max_tool_turns}",
                "code": tool_result.LIMIT_EXCEEDED,
            }))
            return events, log_entries

        except Exception as exc:
            _log("error", f"异常: {exc}")
            events.append(MvuAgentEvent("error", {"message": str(exc)}))
            return events, log_entries
