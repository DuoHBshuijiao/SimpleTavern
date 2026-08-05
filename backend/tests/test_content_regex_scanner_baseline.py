"""T-803-3C: content-regex scanner incremental scan + lock observability baselines."""

from __future__ import annotations

import json
import time
from pathlib import Path

import app.content_regex_scanner as scanner
import app.storage as storage
from app.schemas import Chat, ChatContentRegexRule, ChatMessage, ChatOverrides, Settings


def _patch_paths(monkeypatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    chats = data / "chats"
    chars = data / "characters"
    chats.mkdir(parents=True)
    chars.mkdir(parents=True)
    monkeypatch.setattr(storage, "_data_dir", lambda: data)
    monkeypatch.setattr(storage, "_chats_dir", lambda: chats)
    monkeypatch.setattr(storage, "_characters_dir", lambda: chars)
    return chats


def _make_character(chars: Path, character_id: str) -> None:
    path = chars / f"{character_id}.json"
    path.write_text(
        json.dumps(
            {
                "id": character_id,
                "name": character_id,
                "createdAt": "2026-08-05T00:00:00+00:00",
                "updatedAt": "2026-08-05T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def _make_chat(chats: Path, character_id: str, chat_id: str, *, content: str = "HP: 1") -> Path:
    path = chats / character_id / chat_id / "chat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": chat_id,
                "characterId": character_id,
                "title": chat_id,
                "createdAt": "2026-08-05T00:00:00+00:00",
                "updatedAt": "2026-08-05T00:00:00+00:00",
                "messages": [
                    {"id": f"{chat_id}-g", "role": "assistant", "content": "hi"},
                    {"id": f"{chat_id}-a", "role": "assistant", "content": content},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_iter_chat_record_paths_no_double_load(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    _make_chat(chats, "char-a", "chat-1")
    _make_chat(chats, "char-a", "chat-group")
    group_path = chats / "char-a" / "chat-group" / "chat.json"
    raw = json.loads(group_path.read_text(encoding="utf-8"))
    raw["isGroup"] = True
    group_path.write_text(json.dumps(raw), encoding="utf-8")

    paths = list(storage.iter_chat_record_paths())
    assert len(paths) == 2
    assert {p[1] for p in paths} == {"chat-1", "chat-group"}


def test_scan_mtime_skip_and_health(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    chars = tmp_path / "data" / "characters"
    _make_character(chars, "char-a")
    _make_chat(chats, "char-a", "chat-1", content="HP: 9")

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
    monkeypatch.setattr(scanner, "load_settings", lambda: settings)
    monkeypatch.setattr(
        scanner,
        "resolve_chat_mvu_runtime_enablement",
        lambda _c: type("E", (), {"enabled": False, "character_error": None})(),
    )
    monkeypatch.setattr(scanner, "enqueue_content_regex_items", lambda *_a, **_k: None)

    scanner.reset_scanner_scan_state_for_tests()
    storage.reset_lock_observability()

    cold = scanner._scan_once()
    assert cold["chatsLoaded"] == 1
    assert cold["chatsSkippedUnchanged"] == 0
    assert cold["chatsConsidered"] == 1

    warm = scanner._scan_once()
    assert warm["chatsLoaded"] == 0
    assert warm["chatsSkippedUnchanged"] == 1
    health = scanner.get_content_regex_scanner_health()
    assert "lastScanDurationMs" in health
    assert "lockAcquireCount" in health


def test_signature_written_only_after_successful_apply(monkeypatch) -> None:
    chat = Chat(
        id="chat-fail",
        characterId="char-b",
        overrides=ChatOverrides(),
        messages=[
            ChatMessage(role="assistant", content="hi"),
            ChatMessage(role="assistant", content="HP: 3"),
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
    monkeypatch.setattr(
        scanner,
        "resolve_chat_mvu_runtime_enablement",
        lambda _c: type("E", (), {"enabled": True, "character_error": None})(),
    )
    monkeypatch.setattr(scanner, "_resolve_chat_mvu_scan_mode", lambda _c, _cache: "regex")

    def boom(*_a, **_k):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(scanner, "enqueue_content_regex_items", boom)
    scanner.reset_scanner_scan_state_for_tests()

    try:
        scanner._process_chat(chat, settings, {})
        assert False, "expected enqueue failure"
    except RuntimeError:
        pass
    assert scanner._processed_signatures == {}


def test_scanner_cold_warm_baseline(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    chars = tmp_path / "data" / "characters"
    for i in range(10):
        cid = f"char-{i:02d}"
        _make_character(chars, cid)
        for j in range(10):
            _make_chat(chats, cid, f"chat-{i:02d}-{j:02d}", content=f"HP: {j}")

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
    monkeypatch.setattr(scanner, "load_settings", lambda: settings)
    monkeypatch.setattr(
        scanner,
        "resolve_chat_mvu_runtime_enablement",
        lambda _c: type("E", (), {"enabled": False, "character_error": None})(),
    )
    monkeypatch.setattr(scanner, "enqueue_content_regex_items", lambda *_a, **_k: None)

    scanner.reset_scanner_scan_state_for_tests()
    storage.reset_lock_observability()

    t0 = time.perf_counter()
    cold = scanner._scan_once()
    cold_ms = (time.perf_counter() - t0) * 1000
    assert cold["chatsConsidered"] == 100
    assert cold["chatsLoaded"] == 100
    assert cold_ms < 5000
    print(f"content_regex_scan_cold_100_ms={cold_ms:.2f}")

    t1 = time.perf_counter()
    warm = scanner._scan_once()
    warm_ms = (time.perf_counter() - t1) * 1000
    assert warm["chatsLoaded"] == 0
    assert warm["chatsSkippedUnchanged"] == 100
    assert warm_ms < max(100.0, cold_ms * 0.25)
    print(f"content_regex_scan_warm_100_ms={warm_ms:.2f}")


def test_lock_observability_counts(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    path = _make_chat(chats, "char-z", "chat-z")
    storage.reset_lock_observability()
    storage.read_json(path, shared=True)
    storage.read_json(path, shared=False)
    stats = storage.get_lock_observability()
    assert stats["acquireCount"] >= 2
    assert stats["sharedAcquireCount"] >= 1
    assert stats["exclusiveAcquireCount"] >= 1
