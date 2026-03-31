"""
Tokenizer 服务模块

提供基于 DeepSeek V3 tokenizer 的 token 计数，用于长期记忆与对话长度估算。
Tokenizer 目录：backend/tokenizer/deepseek_v3_tokenizer（与 app 目录同级）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# 从 app 目录定位到 backend/tokenizer/deepseek_v3_tokenizer
_APP_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _APP_DIR.parent
_TOKENIZER_DIR = _BACKEND_DIR / "tokenizer" / "deepseek_v3_tokenizer"

_tokenizer_instance = None


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
    """单条消息的 token 数（role + content，可选 reasoning_content）。"""
    role = msg.get("role", "unknown")
    content = (msg.get("content") or "") or ""
    parts = [f"{role}: {content}"]
    if msg.get("reasoning_content"):
        parts.append(str(msg["reasoning_content"]))
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
