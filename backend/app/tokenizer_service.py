"""
Tokenizer 服务模块

提供基于 DeepSeek V3 tokenizer 的 token 计数，用于长期记忆与对话长度估算。
Tokenizer 目录：backend/tokenizer/deepseek_v3_tokenizer（与 app 目录同级）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.assistant_tool_rounds import segment_openai_messages_for_assistant

# 从 app 目录定位到 backend/tokenizer/deepseek_v3_tokenizer
_APP_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _APP_DIR.parent
_TOKENIZER_DIR = _BACKEND_DIR / "tokenizer" / "deepseek_v3_tokenizer"

_tokenizer_instance = None
_ASSISTANT_TOOL_HISTORY_SUMMARY_PREFIX = "[assistant_tool_history_summary]"
_ASSISTANT_TOOL_SUMMARY_ENTRY_LIMIT = 8
_ASSISTANT_TOOL_SUMMARY_MIN_BUDGET = 16
_ASSISTANT_TOOL_SUMMARY_MAX_BUDGET = 96


def _get_tokenizer():
    """懒加载 tokenizer，失败时返回 None。"""
    global _tokenizer_instance
    if _tokenizer_instance is not None:
        return _tokenizer_instance
    try:
        from tokenizers import Tokenizer
        if not _TOKENIZER_DIR.exists():
            return None
        tokenizer_json = _TOKENIZER_DIR / "tokenizer.json"
        if not tokenizer_json.exists():
            return None
        _tokenizer_instance = Tokenizer.from_file(str(tokenizer_json))
        return _tokenizer_instance
    except Exception:
        return None


def warmup_tokenizer() -> None:
    """
    在应用启动时预加载 tokenizer，避免首次请求时触发 transformers/PyTorch 检查带来的延迟。
    仅尝试加载，失败时静默忽略（后续请求仍会走懒加载逻辑）。
    """
    _get_tokenizer()


def count_tokens(text: str | None) -> int | None:
    """
    计算文本的 token 数。

    Args:
        text: 待计算文本，None 或空串视为 0。

    Returns:
        token 数；若 tokenizer 不可用则返回 None。
    """
    if text is None or not text.strip():
        return 0
    tok = _get_tokenizer()
    if tok is None:
        return None
    try:
        encoded: Any = tok.encode(text)
        ids = getattr(encoded, "ids", None)
        if ids is None:
            return None
        return len(ids)
    except Exception:
        return None


def _count_message_tokens(msg: dict) -> int | None:
    """单条消息的 token 数：role、content、reasoning_content、tool_calls、tool_call_id。"""
    role = msg.get("role", "unknown")
    content = (msg.get("content") or "") or ""
    parts = [f"{role}: {content}"]
    if msg.get("reasoning_content"):
        parts.append(str(msg["reasoning_content"]))
    if msg.get("tool_calls"):
        try:
            parts.append(json.dumps(msg["tool_calls"], ensure_ascii=False))
        except (TypeError, ValueError):
            parts.append(str(msg["tool_calls"]))
    if msg.get("role") == "tool":
        tid = (msg.get("tool_call_id") or "") or ""
        if tid:
            parts.append(f"tool_call_id:{tid}")
    return count_tokens("\n".join(parts))


def count_tokens_for_messages(messages: list[dict]) -> int | None:
    """对消息列表逐条计数并求和，任一失败则返回 None。"""
    total = 0
    for m in messages:
        n = _count_message_tokens(m)
        if n is None:
            return None
        total += n
    return total


def _segment_contains_tool_round(segment: list[dict[str, Any]]) -> bool:
    if not segment:
        return False
    first = segment[0]
    if first.get("role") == "assistant" and first.get("tool_calls"):
        return True
    return any(msg.get("role") == "tool" for msg in segment)


def _tool_result_brief(content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    try:
        raw = json.loads(content)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _tool_name_map_for_segment(segment: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    if not segment:
        return names
    first = segment[0]
    for tc in first.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        tid = str(tc.get("id") or "").strip()
        fn = tc.get("function") or {}
        name = str(fn.get("name") or "").strip()
        if tid and name:
            names[tid] = name
    return names


def _tool_summary_entries_for_segment(segment: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not _segment_contains_tool_round(segment):
        return []
    names = _tool_name_map_for_segment(segment)
    entries: list[dict[str, str]] = []
    for msg in segment:
        if msg.get("role") != "tool":
            continue
        tid = str(msg.get("tool_call_id") or "").strip()
        result = _tool_result_brief(msg.get("content"))
        tool_name = names.get(tid) or str(((result.get("meta") or {}) if isinstance(result.get("meta"), dict) else {}).get("tool") or tid or "unknown_tool")
        code = str(result.get("code") or ("OK" if result.get("ok") is True else "UNKNOWN"))
        message = str(result.get("message") or "").strip()
        entries.append({"tool": tool_name, "code": code, "message": message})
    return entries


def _build_assistant_tool_history_summary(
    dropped_segments: list[list[dict[str, Any]]],
    summary_budget: int,
) -> dict[str, Any] | None:
    if summary_budget < _ASSISTANT_TOOL_SUMMARY_MIN_BUDGET:
        return None
    all_entries: list[dict[str, str]] = []
    for segment in dropped_segments:
        all_entries.extend(_tool_summary_entries_for_segment(segment))
    if not all_entries:
        return None
    recent_entries = all_entries[-_ASSISTANT_TOOL_SUMMARY_ENTRY_LIMIT:]

    def render(entry_count: int, message_limit: int) -> str:
        lines = [
            _ASSISTANT_TOOL_HISTORY_SUMMARY_PREFIX,
            f"Earlier tool rounds were omitted due to context budget. Omitted tool results: {len(all_entries)}.",
        ]
        subset = recent_entries[-entry_count:]
        for idx, entry in enumerate(subset, start=1):
            line = f"{idx}. {entry['tool']} [{entry['code']}]"
            message = entry["message"]
            if message:
                compact = message if len(message) <= message_limit else message[:message_limit].rstrip() + "..."
                line += f" - {compact}"
            lines.append(line)
        return "\n".join(lines)

    max_entry_count = min(len(recent_entries), _ASSISTANT_TOOL_SUMMARY_ENTRY_LIMIT)
    for entry_count in range(max_entry_count, 0, -1):
        for message_limit in (72, 48, 24, 0):
            content = render(entry_count, message_limit)
            token_count = count_tokens(content)
            if token_count is not None and token_count <= summary_budget:
                return {"role": "system", "content": content}
    return None


def _select_segment_indices_with_budget(
    segments: list[list[dict[str, Any]]],
    seg_tokens: list[int],
    budget: int,
) -> tuple[list[int], int]:
    total = 0
    keep_indices: list[int] = []
    for i in range(len(segments) - 1, -1, -1):
        t = seg_tokens[i]
        if total + t <= budget:
            total += t
            keep_indices.append(i)
        else:
            break
    keep_indices.reverse()
    return keep_indices, total


def trim_dict_messages_to_token_budget(
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    从时间顺序列表头部丢弃最旧消息，直到总 token <= max_tokens；保留最新消息。
    tokenizer 不可用时返回原列表并带警告。
    """
    warnings: list[str] = []
    if max_tokens < 1 or not messages:
        return list(messages), warnings
    total = count_tokens_for_messages(messages)
    if total is None:
        warnings.append("token_count_unavailable")
        return list(messages), warnings
    if total <= max_tokens:
        return list(messages), warnings
    kept = list(messages)
    while len(kept) > 1:
        t = count_tokens_for_messages(kept)
        if t is None:
            warnings.append("token_count_unavailable")
            return list(messages), warnings
        if t <= max_tokens:
            return kept, warnings
        kept = kept[1:]
    if kept:
        t1 = count_tokens_for_messages(kept)
        if t1 is not None and t1 > max_tokens:
            warnings.append("single_message_exceeds_token_budget")
    return kept, warnings


def trim_messages_to_context(
    messages: list[dict],
    context_size: int,
    long_term_memory_text: str | None = None,
) -> list[dict]:
    """
    按 context_size 裁剪消息列表：长期记忆长度 + 最近消息（FIFO，从最新往后）<= context_size。

    Args:
        messages: 消息列表，每项为 dict，含 role、content 等。
        context_size: 上下文总限制（token 数）。
        long_term_memory_text: 长期记忆文本，其 token 数占用预算。

    Returns:
        裁剪后的消息列表（保持时间顺序）；若 tokenizer 不可用或 context_size 无效则返回原列表。
    """
    if not messages or context_size < 1:
        return list(messages)
    memory_tokens = count_tokens(long_term_memory_text)
    if memory_tokens is None:
        return list(messages)
    budget = context_size - memory_tokens
    if budget <= 0:
        return []
    # 每条消息的 token 数（从后往前算，便于 FIFO）
    token_counts: list[int | None] = []
    for m in messages:
        n = _count_message_tokens(m)
        token_counts.append(n)
    if any(t is None for t in token_counts):
        return list(messages)
    # 从最新消息往后取，直到超出 budget
    total = 0
    keep_indices: list[int] = []
    for i in range(len(messages) - 1, -1, -1):
        t = token_counts[i]
        if t is None:
            break
        if total + t <= budget:
            total += t
            keep_indices.append(i)
        else:
            break
    keep_indices.reverse()
    return [messages[i] for i in keep_indices]


def trim_assistant_openai_messages_to_context(
    messages: list[dict],
    context_size: int,
    long_term_memory_text: str | None = None,
) -> list[dict]:
    """
    按 context_size 裁剪助手 OpenAI 消息：以「工具轮次段」为原子单元，从最新往旧累加，
    避免只保留半截 assistant.tool_calls 或孤立 role=tool。

    tokenizer 不可用时返回原列表（与 trim_messages_to_context 一致）。
    """
    if not messages or context_size < 1:
        return list(messages)
    memory_tokens = count_tokens(long_term_memory_text)
    if memory_tokens is None:
        return list(messages)
    budget = context_size - memory_tokens
    if budget <= 0:
        return []
    segments = segment_openai_messages_for_assistant(messages)
    seg_tokens: list[int | None] = []
    for seg in segments:
        t = count_tokens_for_messages(seg)
        seg_tokens.append(t)
    if any(t is None for t in seg_tokens):
        return list(messages)

    concrete_seg_tokens = [int(t or 0) for t in seg_tokens]
    keep_seg_indices, kept_total = _select_segment_indices_with_budget(segments, concrete_seg_tokens, budget)

    dropped_segments = segments[: keep_seg_indices[0]] if keep_seg_indices else segments
    if dropped_segments and any(_segment_contains_tool_round(seg) for seg in dropped_segments):
        summary_budget = min(_ASSISTANT_TOOL_SUMMARY_MAX_BUDGET, max(_ASSISTANT_TOOL_SUMMARY_MIN_BUDGET, budget // 12))
        summary_msg = _build_assistant_tool_history_summary(dropped_segments, summary_budget)
        if summary_msg is not None:
            summary_tokens = count_tokens_for_messages([summary_msg])
            if summary_tokens is not None:
                candidate_keep_indices = list(keep_seg_indices)
                candidate_kept_total = kept_total
                while candidate_keep_indices and candidate_kept_total + summary_tokens > budget:
                    removed_idx = candidate_keep_indices.pop(0)
                    candidate_kept_total -= concrete_seg_tokens[removed_idx]
                out: list[dict] = [summary_msg]
                for idx in candidate_keep_indices:
                    out.extend(segments[idx])
                total_tokens = count_tokens_for_messages(out)
                if total_tokens is not None and total_tokens <= budget:
                    return out

    out: list[dict] = []
    for idx in keep_seg_indices:
        out.extend(segments[idx])
    return out
