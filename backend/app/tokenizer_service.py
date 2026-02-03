"""
Tokenizer 服务模块

提供基于 DeepSeek V3 tokenizer 的 token 计数，用于长期记忆与对话长度估算。
Tokenizer 目录：backend/tokenizer/deepseek_v3_tokenizer（与 app 目录同级）。
"""
from __future__ import annotations

from pathlib import Path

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
        from transformers import AutoTokenizer
        if not _TOKENIZER_DIR.exists():
            return None
        _tokenizer_instance = AutoTokenizer.from_pretrained(
            str(_TOKENIZER_DIR),
            trust_remote_code=True,
        )
        return _tokenizer_instance
    except Exception:
        return None


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
        return len(tok.encode(text, add_special_tokens=False))
    except Exception:
        return None
