from app import content_regex_scanner as scanner
from app.schemas import CharacterCard, Chat, ChatContentRegexRule, ChatMessage, ChatOverrides, Settings


def test_scanner_does_not_enqueue_or_signal_directive_mvu(monkeypatch) -> None:
    chat = Chat(
        id="chat-directive-scan",
        characterId="char-directive-scan",
        overrides=ChatOverrides(mvuMode="directive"),
        messages=[
            ChatMessage(role="assistant", content="greeting"),
            ChatMessage(role="assistant", content="HP: 10"),
        ],
    )
    settings = Settings(
        contentRegexRuleLibrary=[
            ChatContentRegexRule(
                id="hp",
                pattern=r"HP: (\d+)",
                action="extract",
                extractSource="capture_group",
                extractGroupIndex=1,
            )
        ]
    )
    character = CharacterCard(id=chat.characterId, name="Directive", mvuEnabled=True, mvuMode="directive")

    enqueued: list[tuple[str, list[dict[str, str]]]] = []
    signaled: list[str] = []

    monkeypatch.setattr(scanner, "load_settings", lambda: settings)
    monkeypatch.setattr(scanner, "_chat_iter", lambda: iter([chat]))
    monkeypatch.setattr(scanner, "is_chat_mvu_runtime_enabled", lambda _chat: True)
    monkeypatch.setattr(scanner, "load_character", lambda _character_id: character)
    monkeypatch.setattr(scanner, "enqueue_content_regex_items", lambda chat_id, items: enqueued.append((chat_id, items)))
    monkeypatch.setattr(
        "app.services.mvu_daemon.signal_queue_threshold",
        lambda chat_id: signaled.append(chat_id),
    )

    scanner._processed_signatures.clear()
    scanner._scan_once()

    assert enqueued == []
    assert signaled == []
