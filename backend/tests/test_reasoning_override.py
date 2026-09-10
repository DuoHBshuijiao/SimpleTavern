"""T-824：会话级 reasoningEffort 覆盖全局。"""

from __future__ import annotations

import pytest

from app.errors import AppError
from app.llm.resolution import _effort_from_settings, clamp_reasoning_effort, prepare_llm_request
from app.schemas import Settings, SettingsLLM


def test_session_override_wins() -> None:
    class Settings:
        reasoningEffort = "high"

    effort, source = _effort_from_settings(Settings(), "none")
    assert effort == "none"
    assert source == "session"


def test_global_used_when_no_override() -> None:
    class Settings:
        reasoningEffort = "medium"

    effort, source = _effort_from_settings(Settings(), None)
    assert effort == "medium"
    assert source == "global"


def test_clamp_none_up_when_unavailable() -> None:
    target, adj = clamp_reasoning_effort("none", ("low", "medium", "high"))
    assert target == "low"
    assert adj and adj["from"] == "none"


def test_prepare_fast_unsupported_raises() -> None:
    settings = Settings(
        llm=SettingsLLM(baseUrl="https://api.deepseek.com/v1", apiKey="k", defaultModel="deepseek-v4-flash"),
    )
    with pytest.raises(AppError) as ei:
        prepare_llm_request(settings, model="deepseek-v4-flash", fast_mode=True)
    assert ei.value.code == "provider_capability_unsupported"
