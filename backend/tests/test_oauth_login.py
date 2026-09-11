"""T-830: OAuth token store, Copilot URL, missing login fast-fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.oauth.copilot import api_base_from_token
from app.llm.oauth.store import load_token, public_status, save_token
from app.llm.preset_resolve import LlmPresetResolveError, resolve_llm_preset_credentials
from app.llm.providers.openai_compatible_chat import _chat_completions_url, _models_url
from app.schemas import ApiPreset, Settings, SettingsLLM


def test_codex_parse_callback_url() -> None:
    from app.llm.oauth.codex import parse_authorization_input

    parsed = parse_authorization_input("http://localhost:1455/auth/callback?code=abc&state=xyz")
    assert parsed["code"] == "abc"
    assert parsed["state"] == "xyz"


def test_copilot_proxy_ep_to_api_host() -> None:
    token = "tid=abc;exp=1;proxy-ep=proxy.individual.githubcopilot.com;other=x"
    assert api_base_from_token(token) == "https://api.individual.githubcopilot.com"


def test_copilot_urls_do_not_gain_v1() -> None:
    base = "https://api.individual.githubcopilot.com"
    assert _chat_completions_url(base) == "https://api.individual.githubcopilot.com/chat/completions"
    assert _models_url(base) == "https://api.individual.githubcopilot.com/models"


def test_oauth_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.storage._data_dir", lambda: tmp_path)
    save_token(
        "preset-1",
        {
            "provider": "github-copilot",
            "accessToken": "copilot-access",
            "refreshToken": "github-refresh",
            "expiresAt": 9_999_999_999_000,
            "accountId": None,
            "enterpriseUrl": None,
        },
    )
    rec = load_token("preset-1")
    assert rec is not None
    assert rec["accessToken"] == "copilot-access"
    status = public_status(rec)
    assert status["loggedIn"] is True
    assert "accessToken" not in status


def test_oauth_preset_without_login_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.storage._data_dir", lambda: tmp_path)
    settings = Settings(
        llm=SettingsLLM(baseUrl="https://global.example", apiKey="g", defaultModel="m"),
        apiPresets=[
            ApiPreset(
                id="copilot",
                name="Copilot",
                baseUrl="https://api.individual.githubcopilot.com",
                apiKey="",
                models=["gpt-4.1"],
                providerId="github-copilot",
                authStyle="oauth_device",
            )
        ],
    )
    with pytest.raises(LlmPresetResolveError) as ei:
        resolve_llm_preset_credentials(settings, explicit_preset_id="copilot")
    assert ei.value.code == "MISSING_OAUTH_LOGIN"


def test_oauth_preset_uses_stored_access(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.storage._data_dir", lambda: tmp_path)
    save_token(
        "copilot",
        {
            "provider": "github-copilot",
            "accessToken": "tid=x;proxy-ep=proxy.individual.githubcopilot.com",
            "refreshToken": "gh",
            "expiresAt": 9_999_999_999_000,
        },
    )
    settings = Settings(
        llm=SettingsLLM(baseUrl="https://global.example", apiKey="g", defaultModel="m"),
        apiPresets=[
            ApiPreset(
                id="copilot",
                name="Copilot",
                baseUrl="https://api.individual.githubcopilot.com",
                apiKey="",
                models=["gpt-4.1"],
                providerId="github-copilot",
                authStyle="oauth_device",
            )
        ],
    )
    creds = resolve_llm_preset_credentials(settings, explicit_preset_id="copilot")
    assert creds.api_key.startswith("tid=")
    assert creds.base_url == "https://api.individual.githubcopilot.com"
    assert creds.extra_headers.get("Copilot-Integration-Id") == "vscode-chat"
