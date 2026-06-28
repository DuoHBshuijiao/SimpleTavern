from app.content_regex import apply_content_regex_pipeline, normalize_replacement_syntax
from app.schemas import ChatContentRegexRule


def _rule(**kwargs) -> ChatContentRegexRule:
    data = {
        "id": kwargs.pop("id", "rule"),
        "enabled": kwargs.pop("enabled", True),
        "order": kwargs.pop("order", 0),
        "pattern": kwargs.pop("pattern", ""),
        "action": kwargs.pop("action", "remove"),
        "replacement": kwargs.pop("replacement", None),
        "matchMode": kwargs.pop("matchMode", "global"),
    }
    data.update(kwargs)
    return ChatContentRegexRule.model_validate(data)


def test_normalize_replacement_syntax_supports_js_groups() -> None:
    assert normalize_replacement_syntax("hello $1 $$ $12") == r"hello \g<1> $ \g<12>"


def test_remove_first_only() -> None:
    result = apply_content_regex_pipeline(
        "one two two",
        [_rule(pattern="two", action="remove", matchMode="first")],
    )

    assert result.display_text == "one  two"
    assert result.persisted_text == "one  two"


def test_replace_js_group_syntax() -> None:
    result = apply_content_regex_pipeline(
        "name: Alice",
        [_rule(pattern=r"name: (\w+)", action="replace", replacement="user=$1")],
    )

    assert result.display_text == "user=Alice"
    assert result.persisted_text == "user=Alice"


def test_extract_and_replace_only_changes_display_text() -> None:
    result = apply_content_regex_pipeline(
        "HP: 10",
        [
            _rule(
                id="hp",
                name="HP",
                pattern=r"HP: (\d+)",
                action="extract_and_replace",
                replacement="[state]",
                extractSource="capture_group",
                extractGroupIndex=1,
            )
        ],
    )

    assert result.persisted_text == "HP: 10"
    assert result.display_text == "[state]"
    assert result.extracted_items[0]["value"] == "10"


def test_invalid_runtime_rule_is_reported_and_next_rule_runs() -> None:
    bad = ChatContentRegexRule.model_construct(
        id="bad",
        name="bad",
        enabled=True,
        order=0,
        pattern="[",
        action="remove",
        replacement=None,
        matchMode="global",
    )
    good = _rule(id="good", order=1, pattern="ok", action="replace", replacement="done")

    result = apply_content_regex_pipeline("ok", [bad, good])

    assert result.display_text == "done"
    assert result.errors[0]["errorCode"] == "REGEX_INVALID"
