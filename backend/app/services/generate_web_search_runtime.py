"""
主聊天生成：可选两轮 web_search 工具（首轮 tools + 次轮纯文本）。
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, AsyncIterator
from uuid import uuid4

from app.llm.openai_compat import chat_completions_message, stream_chat_completions
from app.schemas import Settings
from app.services.web_search import OPENAI_WEB_SEARCH_TOOLS, run_web_search, web_search_is_configured


def normalize_tool_calls_ids(tool_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """为每条 tool_call 补全非空 id，保证与 role=tool 的 tool_call_id 一致。"""
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


async def iter_web_search_stream_events(
    *,
    messages: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    extra_body: dict[str, Any],
    settings: Settings,
    web_search_enabled: bool,
) -> AsyncIterator[dict[str, Any]]:
    """
    Yields:
      {"type": "reasoning", "text": str}
      {"type": "delta", "text": str}
      {"type": "done", "content_saved": str, "reasoning_full": str | None, "reasoning_duration_sec": float | None}
    """
    msgs = deepcopy(messages)
    max_rounds = 2 if (web_search_enabled and web_search_is_configured(settings)) else 1
    full_reasoning: list[str] = []
    reasoning_start: float | None = None
    reasoning_end: float | None = None

    for round_idx in range(max_rounds):
        use_tools = max_rounds == 2 and round_idx == 0
        eb = dict(extra_body or {})
        if use_tools:
            eb["tool_choice"] = "auto"
        tools = OPENAI_WEB_SEARCH_TOOLS if use_tools else None
        round_content: list[str] = []
        finish_tc = None

        async for chunk in stream_chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=msgs,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            extra_body=eb,
        ):
            if chunk.kind == "reasoning":
                now = time.monotonic()
                if reasoning_start is None:
                    reasoning_start = now
                reasoning_end = now
                full_reasoning.append(chunk.text)
                yield {"type": "reasoning", "text": chunk.text}
            elif chunk.kind == "content":
                round_content.append(chunk.text)
                yield {"type": "delta", "text": chunk.text}
            elif chunk.kind == "finish":
                finish_tc = chunk.tool_calls

        if use_tools and finish_tc:
            norm = normalize_tool_calls_ids(finish_tc)
            if norm:
                text_blob = "".join(round_content)
                asst: dict[str, Any] = {"role": "assistant", "content": text_blob or None}
                asst["tool_calls"] = norm
                msgs.append(asst)
                for tc in norm:
                    fn = tc.get("function") or {}
                    name = str(fn.get("name") or "")
                    raw_args = str(fn.get("arguments") or "{}")
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                    q = str(args.get("query") or "").strip()
                    if name == "web_search":
                        body = await run_web_search(settings, q)
                    else:
                        body = json.dumps(
                            {"ok": False, "error": f"未知工具: {name}"},
                            ensure_ascii=False,
                        )
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": body})
                continue

        reasoning_full = "".join(full_reasoning).strip()
        saved_content = "".join(round_content).strip()
        dur: float | None = None
        if reasoning_start is not None and reasoning_end is not None and reasoning_full:
            dur = round(max(0.0, reasoning_end - reasoning_start), 1)
        yield {
            "type": "done",
            "reasoning_full": reasoning_full or None,
            "content_saved": saved_content,
            "reasoning_duration_sec": dur,
        }
        return


async def nonstream_web_search_rounds(
    *,
    messages: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    extra_body: dict[str, Any],
    settings: Settings,
    web_search_enabled: bool,
) -> tuple[str, str | None, float | None]:
    """
    非流式两轮。
    返回 (assistant 正文, reasoning 全文或 None, reasoning 耗时秒或 None)。
    """
    msgs = deepcopy(messages)
    max_rounds = 2 if (web_search_enabled and web_search_is_configured(settings)) else 1
    reasoning_parts: list[str] = []
    req_start = time.monotonic()

    for round_idx in range(max_rounds):
        use_tools = max_rounds == 2 and round_idx == 0
        eb = dict(extra_body or {})
        if use_tools:
            eb["tool_choice"] = "auto"
        tools = OPENAI_WEB_SEARCH_TOOLS if use_tools else None
        resp = await chat_completions_message(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=msgs,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            tools=tools,
            extra_body=eb,
        )
        rc = resp.reasoning_content
        if isinstance(rc, str) and rc:
            reasoning_parts.append(rc)

        if use_tools and resp.tool_calls:
            norm = normalize_tool_calls_ids(resp.tool_calls)
            if norm:
                asst = {"role": "assistant", "content": resp.content or None, "tool_calls": norm}
                msgs.append(asst)
                for tc in norm:
                    fn = tc.get("function") or {}
                    name = str(fn.get("name") or "")
                    raw_args = str(fn.get("arguments") or "{}")
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                    q = str(args.get("query") or "").strip()
                    if name == "web_search":
                        body = await run_web_search(settings, q)
                    else:
                        body = json.dumps(
                            {"ok": False, "error": f"未知工具: {name}"},
                            ensure_ascii=False,
                        )
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": body})
                continue

        content_final = (resp.content or "").strip()
        reasoning_full = "".join(reasoning_parts).strip() or None
        dur = round(max(0.0, time.monotonic() - req_start), 1) if reasoning_full else None
        return content_final, reasoning_full, dur

    return "", None, None
