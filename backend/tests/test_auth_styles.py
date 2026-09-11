"""T-820-A2：AuthStyle / URL 模板 / Bedrock Anthropic 变体。"""

from __future__ import annotations

from app.llm.providers.anthropic_messages import AnthropicMessagesAdapter
from app.llm.providers.gemini_generate_content import GeminiGenerateContentAdapter
from app.llm.providers.openai_compatible_chat import _request_url_and_headers
from app.llm.types import (
    GenerationConfig,
    append_api_version,
    append_query_key,
    auth_headers_for_style,
)


def test_auth_headers_by_style() -> None:
    assert auth_headers_for_style("k", "bearer") == {"Authorization": "Bearer k"}
    assert auth_headers_for_style("k", "x-api-key") == {"x-api-key": "k"}
    assert auth_headers_for_style("k", "api-key") == {"api-key": "k"}
    assert auth_headers_for_style("k", "x-goog-api-key") == {"x-goog-api-key": "k"}
    assert auth_headers_for_style("k", "query_key") == {}
    assert auth_headers_for_style("k", "oauth_device") == {"Authorization": "Bearer k"}
    assert auth_headers_for_style("k", "oauth_pkce") == {"Authorization": "Bearer k"}
    assert auth_headers_for_style("", "oauth_device") == {}


def test_query_key_and_api_version() -> None:
    url = append_query_key("https://generativelanguage.googleapis.com/v1beta/models", "abc", "query_key")
    assert "key=abc" in url
    azure = append_api_version(
        "https://my.openai.azure.com/openai/v1/chat/completions",
        {"api_version": "2024-10-21"},
    )
    assert "api-version=2024-10-21" in azure
    chat_url, headers = _request_url_and_headers(
        "https://my.openai.azure.com/openai/v1",
        "azure-key",
        accept="application/json",
        auth_style="api-key",
        provider_params={"api_version": "2024-10-21"},
    )
    assert headers["api-key"] == "azure-key"
    assert "Authorization" not in headers
    assert "api-version=2024-10-21" in chat_url


def test_bedrock_anthropic_variant_drops_model() -> None:
    adapter = AnthropicMessagesAdapter()
    req = adapter.build_request(
        base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        api_key="bedrock-token",
        messages=[{"role": "user", "content": "hi"}],
        config=GenerationConfig(
            model="anthropic.claude-sonnet-4-6",
            protocol_variant="bedrock",
            auth_style="bearer",
        ),
    )
    assert "/model/anthropic.claude-sonnet-4-6/invoke" in req.url
    assert req.headers.get("Authorization") == "Bearer bedrock-token"
    assert "x-api-key" not in {k.lower() for k in req.headers}
    assert "model" not in req.json_body
    assert req.json_body["anthropic_version"] == "bedrock-2023-05-31"


def test_gemini_query_key_auth_style() -> None:
    adapter = GeminiGenerateContentAdapter()
    req = adapter.build_request(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gemini-key",
        messages=[{"role": "user", "content": "hi"}],
        config=GenerationConfig(model="gemini-2.5-flash", auth_style="query_key"),
    )
    assert "key=gemini-key" in req.url
    assert "x-goog-api-key" not in {k.lower() for k in req.headers}
    assert "Authorization" not in req.headers
