"""T-822：clamp_reasoning_effort 档位收敛。"""

from __future__ import annotations

from app.llm.resolution import clamp_reasoning_effort


def test_max_clamps_down() -> None:
    target, adj = clamp_reasoning_effort("max", ("none", "low", "medium", "high"))
    assert target == "high"
    assert adj and adj["from"] == "max" and adj["to"] == "high"


def test_available_passthrough() -> None:
    target, adj = clamp_reasoning_effort("low", ("none", "low", "high"))
    assert target == "low"
    assert adj is None
