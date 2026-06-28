import re

from app.regex_compat import compile_user_regex, split_regex_literal


def test_split_regex_literal_accepts_safe_flags() -> None:
    parsed = split_regex_literal("/foo/im")

    assert parsed is not None
    pattern, flags = parsed
    assert pattern == "foo"
    assert flags & re.IGNORECASE
    assert flags & re.MULTILINE


def test_split_regex_literal_ignores_slash_inside_character_class() -> None:
    parsed = split_regex_literal("/[a/z]+/s")

    assert parsed is not None
    assert parsed[0] == "[a/z]+"
    assert parsed[1] & re.DOTALL


def test_split_regex_literal_rejects_unsafe_or_duplicate_flags() -> None:
    assert split_regex_literal("/foo/g") is None
    assert split_regex_literal("/foo/ii") is None
    assert split_regex_literal("/foo/i1") is None


def test_compile_user_regex_falls_back_to_raw_pattern() -> None:
    compiled = compile_user_regex("foo", re.MULTILINE)

    assert compiled.search("foo")
    assert compiled.flags & re.MULTILINE
