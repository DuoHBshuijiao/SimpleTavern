"""TXT (Version 2) chat import should surface transcript row warnings instead of dropping them."""

from __future__ import annotations

from app.routes import import_export as ie
from app.schemas import CharacterCard, Settings


def _v2_text() -> str:
    return "\n".join([
        "SimpleTavern Chat Export",
        "Version: 2",
        "ChatId: c1",
        "Title: T",
        "IsGroup: false",
        "Participants: Hero",
        "",
        "[Message]",
        "role=user",
        "content:",
        "<<<",
        "hello",
        ">>>",
        "",
        "[Message]",
        "role=badrole",
        "name=x",
        "content:",
        "<<<",
        "oops",
        ">>>",
        "",
        "[Message]",
        "role=assistant",
        "name=Hero",
        "content:",
        "<<<",
        "hi",
        ">>>",
    ])


def test_parse_chat_text_v2_surfaces_transcript_warnings(monkeypatch):
    monkeypatch.setattr(ie, "list_characters", lambda: [CharacterCard(id="h1", name="Hero")])
    monkeypatch.setattr(ie, "load_settings", lambda: Settings())

    chat, warnings = ie._parse_chat_text(_v2_text())

    # 未知 role 的行应被跳过并产生 warning（此前 TXT 路径会静默丢弃）
    assert any("badrole" in w for w in warnings)
    # 仅保留合法的 user + assistant 两条
    assert len(chat.messages) == 2
    assert [m.role for m in chat.messages] == ["user", "assistant"]
