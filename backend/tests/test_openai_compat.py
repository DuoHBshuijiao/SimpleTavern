from app.llm.openai_compat import (
    _build_payload,
    _chat_completions_url,
    _models_url,
    _upstream_http_error_text,
)


def test_chat_completions_url_adds_openai_v1_for_bare_host() -> None:
    assert _chat_completions_url("api.openai.com") == "https://api.openai.com/v1/chat/completions"


def test_chat_completions_url_preserves_provider_path() -> None:
    assert (
        _chat_completions_url("https://generativelanguage.googleapis.com/v1beta/openai")
        == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )


def test_chat_completions_url_does_not_duplicate_suffix() -> None:
    url = "https://example.com/v1/chat/completions"

    assert _chat_completions_url(url) == url
    assert _models_url(url) == "https://example.com/v1/models"


def test_upstream_http_error_text_extracts_openai_message() -> None:
    assert _upstream_http_error_text('{"error":{"message":"bad key","code":"401"}}') == "bad key: 401"


def test_build_payload_sets_max_completion_tokens_alias() -> None:
    payload = _build_payload(
        model="model",
        messages=[],
        stream=False,
        temperature=None,
        top_p=None,
        max_tokens=32,
        tools=None,
        extra_body=None,
    )

    assert payload["max_tokens"] == 32
    assert payload["max_completion_tokens"] == 32
