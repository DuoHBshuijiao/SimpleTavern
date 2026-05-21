"""Load the MVU agent system prompt from MVU_AGENT.md."""

from __future__ import annotations

import re
from pathlib import Path

_MVU_AGENT_MD = Path(__file__).resolve().parent / "MVU_AGENT.md"
_KG_SECTION_RE = re.compile(
    r"<!--\s*KG_START\s*-->.*?<!--\s*KG_END\s*-->",
    re.DOTALL,
)


def _strip_kg_sections(text: str) -> str:
    cleaned = _KG_SECTION_RE.sub("", text)
    # 工作流程去掉 KG 步骤后，重编号 7 -> 6
    cleaned = cleaned.replace(
        "7. 如需要，调用 `read_mvu_logs`",
        "6. 如需要，调用 `read_mvu_logs`",
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"


def load_mvu_system_prompt(*, include_knowledge_graph: bool = True) -> str:
    if not _MVU_AGENT_MD.is_file():
        raise FileNotFoundError(f"MVU agent system prompt file not found: {_MVU_AGENT_MD}")
    text = _MVU_AGENT_MD.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"MVU agent system prompt file is empty: {_MVU_AGENT_MD}")
    if include_knowledge_graph:
        return text
    return _strip_kg_sections(text)
