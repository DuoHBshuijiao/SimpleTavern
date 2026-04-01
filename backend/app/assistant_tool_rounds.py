"""
将助手 OpenAI 风格消息列表划分为「可原子保留」的段，供按段裁剪上下文。

与 OpenAI 约束一致：含 tool_calls 的 assistant 与对应 role=tool 子消息同进同退；
不完整链降级为单条段，避免裁剪时破坏语义或无限丢弃历史。
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def _tool_call_ids_from_assistant(msg: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        tid = str(tc.get("id") or "").strip()
        if tid:
            out.append(tid)
    return out


def segment_openai_messages_for_assistant(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """
    将时间序 OpenAI 消息列表划分为若干段。

    - 普通段：单条 user / assistant（无 tool_calls）/ system。
    - 工具轮次段：一条带非空 tool_calls 的 assistant，且紧跟的若干条 role=tool
      的 tool_call_id 集合与 assistant.tool_calls[].id 一致（每条 id 恰好出现一次）。
    - 不完整或 id 不匹配时采用策略 (a)：该轮次拆成单条消息各占一段（见模块注释）。
    """
    segments: list[list[dict[str, Any]]] = []
    i = 0
    n = len(messages)
    while i < n:
        m = messages[i]
        if (
            m.get("role") == "assistant"
            and m.get("tool_calls")
            and isinstance(m.get("tool_calls"), list)
            and len(m.get("tool_calls") or []) > 0
        ):
            expected_ids = _tool_call_ids_from_assistant(m)
            if not expected_ids:
                segments.append([m])
                i += 1
                continue
            expected_set = set(expected_ids)
            if len(expected_ids) != len(expected_set):
                _logger.debug("assistant tool_calls contains duplicate ids, degrading to single segments")
                segments.append([m])
                i += 1
                continue
            remaining: set[str] = set(expected_ids)
            collected: list[dict[str, Any]] = []
            j = i + 1
            while j < n and messages[j].get("role") == "tool":
                tid = str(messages[j].get("tool_call_id") or "").strip()
                if tid not in expected_set:
                    _logger.debug(
                        "assistant tool round: tool_call_id %r not in expected set, degrading to single segments",
                        tid,
                    )
                    break
                if tid not in remaining:
                    _logger.debug(
                        "assistant tool round: duplicate or unexpected order for tool_call_id %r, degrading",
                        tid,
                    )
                    break
                collected.append(messages[j])
                remaining.discard(tid)
                j += 1

            if not remaining and len(collected) == len(expected_ids):
                segments.append([m] + collected)
                i = j
            else:
                _logger.debug(
                    "assistant tool round incomplete (remaining_ids=%s), degrading to single-message segments",
                    remaining,
                )
                segments.append([m])
                i += 1
            continue

        segments.append([m])
        i += 1
    return segments
