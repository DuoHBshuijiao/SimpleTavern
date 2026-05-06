"""Assistant agent loop service for tool-enabled multi-turn execution."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Literal
from uuid import uuid4

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.digest import args_digest as _tool_args_digest
from app.assistant_tools.executor import build_openai_tools_list, execute_tool
from app.assistant_tools import result as tool_result
from app.llm.openai_compat import chat_completions_message, stream_chat_completions
from app.schemas import AssistantChat, ChatMessage


AssistantChatLoader = Callable[[], AssistantChat]
AssistantChatSaver = Callable[[AssistantChat], AssistantChat]


@dataclass(frozen=True)
class AssistantAgentEvent:
    kind: Literal[
        "reasoning",
        "delta",
        "tool_record",
        "tool_trace",
        "card",
        "chat_memory_updated",
        "worldbook_updated",
        "chat_overrides_updated",
        "done",
        "error",
    ]
    data: dict[str, Any]


@dataclass(frozen=True)
class AssistantAgentRunResult:
    ok: bool
    content: str = ""
    message_id: str | None = None
    tool_traces: list[dict[str, Any]] = field(default_factory=list)
    tool_records: list[dict[str, Any]] = field(default_factory=list)
    card: dict[str, Any] | None = None
    worldbook_updated: list[dict[str, Any]] = field(default_factory=list)
    chat_overrides_updated: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class AssistantAgentRunContext:
    base_url: str
    api_key: str
    model: str
    temperature: float | None
    messages: list[dict[str, Any]]
    extra_body: dict[str, Any]
    tool_ctx: AssistantToolContext
    load_chat: AssistantChatLoader
    save_chat: AssistantChatSaver
    max_tool_turns: int = 8
    max_tools_per_turn: int | None = None

    def tools(self) -> list[dict[str, Any]]:
        return build_openai_tools_list(self.tool_ctx)


def normalize_tool_calls_ids(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """为每条 tool_call 补全非空 id，保证与落库的 role=tool.tool_call_id 一致。"""
    if not tool_calls:
        return []
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        tc_copy = dict(tc) if isinstance(tc, dict) else {}
        tid = str(tc_copy.get("id") or "").strip()
        if not tid:
            tid = f"call_{uuid4().hex}"
        tc_copy["id"] = tid
        out.append(tc_copy)
    return out


def tool_record_payload(
    tool_name: str,
    loop_index: int,
    result: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    msg = str(result.get("message") or "")
    return {
        "toolName": tool_name,
        "loopIndex": loop_index,
        "ok": bool(result.get("ok")),
        "code": result.get("code"),
        "message": msg,
        "argsDigest": _tool_args_digest(args),
    }


def _loop_limit_result(limit: int) -> dict[str, Any]:
    return tool_result.err(
        tool_result.LIMIT_EXCEEDED,
        f"tool call loop limit exceeded: maxToolTurns={limit}",
        tool="assistant_agent",
        details={"maxToolTurns": limit},
    )


def _per_turn_limit_result(tool_name: str, limit: int) -> dict[str, Any]:
    return tool_result.err(
        tool_result.LIMIT_EXCEEDED,
        f"maxToolsPerTurn exceeded; skipped remaining tool call for {tool_name}",
        tool=tool_name,
        details={"maxToolsPerTurn": limit},
    )


class AssistantAgentService:
    """Runs the assistant loop and persists assistant/tool transcript messages."""

    def __init__(self, ctx: AssistantAgentRunContext):
        self._ctx = ctx
        self._tools = ctx.tools()

    async def run_nonstream(self) -> AssistantAgentRunResult:
        current_messages = list(self._ctx.messages)
        tool_traces: list[dict[str, Any]] = []
        wb_updates: list[dict[str, Any]] = []
        co_updates: list[dict[str, Any]] = []
        last_card: dict[str, Any] | None = None

        try:
            for _ in range(self._ctx.max_tool_turns):
                resp = await chat_completions_message(
                    base_url=self._ctx.base_url,
                    api_key=self._ctx.api_key,
                    model=self._ctx.model,
                    messages=current_messages,
                    temperature=self._ctx.temperature,
                    tools=self._tools,
                    extra_body=self._ctx.extra_body,
                )
                tool_calls_raw = resp.tool_calls
                tool_calls_for_llm = (
                    normalize_tool_calls_ids(tool_calls_raw) if tool_calls_raw is not None else None
                )
                llm_assistant_msg: dict[str, Any] = {
                    "role": resp.role or "assistant",
                    "content": resp.content or "",
                }
                if resp.reasoning_content:
                    llm_assistant_msg["reasoning_content"] = resp.reasoning_content
                if tool_calls_for_llm is not None:
                    llm_assistant_msg["tool_calls"] = tool_calls_for_llm
                current_messages.append(llm_assistant_msg)

                if not tool_calls_raw:
                    rc_strip = (resp.reasoning_content or "").strip()
                    if rc_strip:
                        self._append_message(
                            ChatMessage(
                                role="reasoning",
                                content=rc_strip,
                                reasoningDurationSec=None,
                            )
                        )
                    assistant_msg = ChatMessage(
                        role=resp.role or "assistant",
                        content=resp.content or "",
                        reasoningContent=None,
                    )
                    self._append_message(assistant_msg)
                    return AssistantAgentRunResult(
                        ok=True,
                        content=resp.content or "",
                        message_id=assistant_msg.id,
                        tool_traces=tool_traces,
                        tool_records=list(tool_traces),
                        card=last_card,
                        worldbook_updated=wb_updates,
                        chat_overrides_updated=co_updates,
                    )

                rc_strip = (resp.reasoning_content or "").strip()
                if rc_strip:
                    self._append_message(
                        ChatMessage(
                            role="reasoning",
                            content=rc_strip,
                            reasoningDurationSec=None,
                        )
                    )
                self._append_message(
                    ChatMessage(
                        role=resp.role or "assistant",
                        content=resp.content or "",
                        tool_calls=list(tool_calls_for_llm or []),
                        reasoningContent=None,
                    )
                )
                executed, _ = self._execute_tool_calls(
                    tool_calls_for_llm or [],
                    current_messages,
                    start_index=len(tool_traces),
                )
                for item in executed:
                    tool_traces.append(item.trace)
                    if item.card:
                        last_card = item.card
                    if item.worldbook_updated:
                        wb_updates.append(item.worldbook_updated)
                    if item.chat_overrides_updated:
                        co_updates.append(item.chat_overrides_updated)

            loop_limit = _loop_limit_result(self._ctx.max_tool_turns)
            return AssistantAgentRunResult(
                ok=False,
                error=str(loop_limit.get("message") or "tool call loop limit exceeded"),
                error_code=str(loop_limit.get("code") or tool_result.LIMIT_EXCEEDED),
                tool_traces=tool_traces,
                tool_records=list(tool_traces),
            )
        except Exception as exc:
            return AssistantAgentRunResult(ok=False, error=str(exc))

    async def iter_events(self) -> AsyncIterator[AssistantAgentEvent]:
        current_messages = list(self._ctx.messages)
        tool_idx = 0

        for _ in range(self._ctx.max_tool_turns):
            final_content = ""
            final_reasoning_content = ""
            llm_assistant_msg: dict[str, Any] = {"role": "assistant", "content": ""}
            tool_calls_from_stream: list[dict[str, Any]] | None = None
            normalized_stream: list[dict[str, Any]] = []

            reasoning_phase_started: float | None = None
            reasoning_phase_end: float | None = None
            try:
                async for chunk in stream_chat_completions(
                    base_url=self._ctx.base_url,
                    api_key=self._ctx.api_key,
                    model=self._ctx.model,
                    messages=current_messages,
                    temperature=self._ctx.temperature,
                    tools=self._tools,
                    extra_body=self._ctx.extra_body,
                ):
                    if chunk.kind == "reasoning":
                        if reasoning_phase_started is None:
                            reasoning_phase_started = time.monotonic()
                        final_reasoning_content += chunk.text
                        yield AssistantAgentEvent("reasoning", {"text": chunk.text})
                    elif chunk.kind == "content":
                        if reasoning_phase_started is not None and reasoning_phase_end is None:
                            reasoning_phase_end = time.monotonic()
                        final_content += chunk.text
                        yield AssistantAgentEvent("delta", {"text": chunk.text})
                    elif chunk.kind == "finish":
                        tool_calls_from_stream = chunk.tool_calls
            except Exception as exc:
                yield AssistantAgentEvent("error", {"message": str(exc)})
                return

            reasoning_duration_sec: float | None = None
            if reasoning_phase_started is not None:
                end_mono = reasoning_phase_end if reasoning_phase_end is not None else time.monotonic()
                reasoning_duration_sec = round(end_mono - reasoning_phase_started, 3)

            if final_reasoning_content:
                llm_assistant_msg["reasoning_content"] = final_reasoning_content
            llm_assistant_msg["content"] = final_content
            if tool_calls_from_stream:
                normalized_stream = normalize_tool_calls_ids(tool_calls_from_stream)
                llm_assistant_msg["tool_calls"] = normalized_stream
            current_messages.append(llm_assistant_msg)

            frc_strip = final_reasoning_content.strip()
            if frc_strip:
                self._append_message(
                    ChatMessage(
                        role="reasoning",
                        content=frc_strip,
                        reasoningDurationSec=reasoning_duration_sec,
                    )
                )

            if not tool_calls_from_stream:
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=final_content,
                    reasoningContent=None,
                )
                self._append_message(assistant_msg)
                yield AssistantAgentEvent("done", {"ok": True, "messageId": assistant_msg.id})
                return

            self._append_message(
                ChatMessage(
                    role="assistant",
                    content=final_content or "",
                    tool_calls=list(normalized_stream),
                    reasoningContent=None,
                )
            )

            executed, tool_idx = self._execute_tool_calls(
                normalized_stream,
                current_messages,
                start_index=tool_idx,
            )
            for item in executed:
                yield AssistantAgentEvent("tool_record", item.trace)
                yield AssistantAgentEvent("tool_trace", item.trace)
                if item.card:
                    yield AssistantAgentEvent("card", {"card": item.card})
                if item.chat_memory_updated:
                    yield AssistantAgentEvent(
                        "chat_memory_updated",
                        {"chat": item.chat_memory_updated},
                    )
                if item.worldbook_updated:
                    yield AssistantAgentEvent("worldbook_updated", item.worldbook_updated)
                if item.chat_overrides_updated:
                    yield AssistantAgentEvent("chat_overrides_updated", item.chat_overrides_updated)

        loop_limit = _loop_limit_result(self._ctx.max_tool_turns)
        yield AssistantAgentEvent(
            "error",
            {
                "message": loop_limit.get("message") or "tool call loop limit exceeded",
                "code": loop_limit.get("code") or tool_result.LIMIT_EXCEEDED,
                "details": loop_limit.get("details") or {},
            },
        )

    def _append_message(self, message: ChatMessage) -> None:
        chat = self._ctx.load_chat()
        chat.messages.append(message)
        self._ctx.save_chat(chat)

    def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        current_messages: list[dict[str, Any]],
        *,
        start_index: int,
    ) -> tuple[list[_ExecutedToolCall], int]:
        executed: list[_ExecutedToolCall] = []
        tool_idx = start_index
        max_tools_per_turn = self._ctx.max_tools_per_turn
        for turn_index, tool_call in enumerate(tool_calls):
            fn = (tool_call.get("function") or {}).get("name")
            raw_args = (tool_call.get("function") or {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}
            tool_name = str(fn)
            if max_tools_per_turn is not None and turn_index >= max_tools_per_turn:
                result = _per_turn_limit_result(tool_name, max_tools_per_turn)
                outcome = _ExecutedToolOutcome(
                    result=result,
                    card=None,
                    chat_memory_updated=None,
                    worldbook_updated=None,
                    chat_overrides_updated=None,
                )
            else:
                exec_outcome = execute_tool(tool_name, args, self._ctx.tool_ctx)
                outcome = _ExecutedToolOutcome(
                    result=exec_outcome.result,
                    card=exec_outcome.card,
                    chat_memory_updated=exec_outcome.chat_memory_updated,
                    worldbook_updated=exec_outcome.worldbook_updated,
                    chat_overrides_updated=exec_outcome.chat_overrides_updated,
                )
            result = outcome.result
            tid = str(tool_call.get("id") or "").strip()
            record = tool_record_payload(tool_name, tool_idx, result, args)
            tool_msg = ChatMessage(
                role="tool",
                tool_call_id=tid,
                content=json.dumps(result, ensure_ascii=False),
                toolRecord=record,
            )
            self._append_message(tool_msg)
            trace = {
                "record": record,
                "messageId": tool_msg.id,
                "content": tool_msg.content,
            }
            current_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            executed.append(
                _ExecutedToolCall(
                    trace=trace,
                    card=outcome.card,
                    chat_memory_updated=outcome.chat_memory_updated,
                    worldbook_updated=outcome.worldbook_updated,
                    chat_overrides_updated=outcome.chat_overrides_updated,
                )
            )
            tool_idx += 1
        return executed, tool_idx


@dataclass(frozen=True)
class _ExecutedToolCall:
    trace: dict[str, Any]
    card: dict[str, Any] | None
    chat_memory_updated: dict[str, Any] | None
    worldbook_updated: dict[str, Any] | None
    chat_overrides_updated: dict[str, Any] | None


@dataclass(frozen=True)
class _ExecutedToolOutcome:
    result: dict[str, Any]
    card: dict[str, Any] | None
    chat_memory_updated: dict[str, Any] | None
    worldbook_updated: dict[str, Any] | None
    chat_overrides_updated: dict[str, Any] | None