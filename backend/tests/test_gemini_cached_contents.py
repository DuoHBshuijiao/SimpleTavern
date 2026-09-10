"""T-821 Gemini cachedContents 索引。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.gemini_cache_store import attach_explicit_cache, fingerprint, forget, lookup, remember
from app.llm.prompt_cache import PromptCachePlan


def test_fingerprint_stable() -> None:
    a = fingerprint(model="gemini-2.5-flash", system_instruction={"parts": [{"text": "s"}]}, tools=None)
    b = fingerprint(model="gemini-2.5-flash", system_instruction={"parts": [{"text": "s"}]}, tools=None)
    c = fingerprint(model="gemini-2.5-flash", system_instruction={"parts": [{"text": "other"}]}, tools=None)
    assert a == b
    assert a != c


def test_index_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gemini_cache_store._index_path", lambda: tmp_path / "llm_cache_index.json")
    fp = "abc"
    assert lookup(fp) is None
    remember(fp, "cachedContents/xyz", model="gemini-2.5-flash", ttl_seconds=3600)
    assert lookup(fp) == "cachedContents/xyz"
    forget(fp)
    assert lookup(fp) is None


@pytest.mark.asyncio
async def test_attach_creates_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gemini_cache_store._index_path", lambda: tmp_path / "llm_cache_index.json")
    plan = PromptCachePlan(protocol="gemini_generate_content", mode="explicit", ttl=3600)
    payload = {
        "systemInstruction": {"parts": [{"text": "sys"}]},
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
    }
    with patch("app.llm.gemini_cache_store.create_cached_content", new=AsyncMock(return_value="cachedContents/new")):
        out = await attach_explicit_cache(
            payload,
            plan=plan,
            api_root="https://generativelanguage.googleapis.com/v1beta",
            api_key="k",
            model="gemini-2.5-flash",
        )
    assert out["cachedContent"] == "cachedContents/new"
    assert "systemInstruction" not in out
    assert lookup(fingerprint(model="gemini-2.5-flash", system_instruction={"parts": [{"text": "sys"}]}, tools=None))


@pytest.mark.asyncio
async def test_implicit_does_not_create() -> None:
    plan = PromptCachePlan(protocol="gemini_generate_content", mode="implicit")
    payload = {"systemInstruction": {"parts": [{"text": "sys"}]}, "contents": []}
    with patch("app.llm.gemini_cache_store.create_cached_content", new=MagicMock()) as create:
        out = await attach_explicit_cache(
            payload,
            plan=plan,
            api_root="https://generativelanguage.googleapis.com/v1beta",
            api_key="k",
            model="gemini-2.5-flash",
        )
    create.assert_not_called()
    assert out is payload or "cachedContent" not in out
