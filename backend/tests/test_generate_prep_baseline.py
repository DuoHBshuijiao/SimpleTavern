"""T-803-3D: generate worldbook/trim prep profiling + indexed load baselines."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import app.storage as storage
import app.worldbook_index as wbi
from app.routes import generate as gen
from app.schemas import Chat, ChatOverrides, Settings
from app.services import mvu_daemon


def _patch_data(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    chats = data / "chats"
    chars = data / "characters"
    books = data / "worldbooks"
    for d in (chats, chars, books):
        d.mkdir(parents=True)
    monkeypatch.setattr(storage, "_data_dir", lambda: data)
    monkeypatch.setattr(storage, "_chats_dir", lambda: chats)
    monkeypatch.setattr(storage, "_characters_dir", lambda: chars)
    monkeypatch.setattr(storage, "_worldbooks_dir", lambda: books)
    wbi._index_dirty = False
    wbi._memory_cache = None
    wbi._memory_mtime_ns = None
    return chats, books


def _write_book(books: Path, book_id: str, *, global_active: bool = False, session_ids: list[str] | None = None) -> None:
    entries = [
        {
            "id": f"{book_id}-e{i}",
            "regex": r"keyword",
            "content": f"lore-{book_id}-{i} " + ("x" * 40),
            "enabled": True,
            "orderIndex": i,
        }
        for i in range(10)
    ]
    payload = {
        "id": book_id,
        "name": book_id,
        "globalActive": global_active,
        "sessionChatIds": session_ids or [],
        "entries": entries,
        "createdAt": "2026-08-05T00:00:00+00:00",
        "updatedAt": "2026-08-05T00:00:00+00:00",
    }
    (books / f"{book_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_worldbook_index_lists_only_active_ids(monkeypatch, tmp_path) -> None:
    _chats, books = _patch_data(monkeypatch, tmp_path)
    _write_book(books, "wb-global", global_active=True)
    _write_book(books, "wb-session", session_ids=["chat-1"])
    _write_book(books, "wb-idle", global_active=False)
    rebuilt = wbi.rebuild_worldbook_index()
    assert set(rebuilt["byId"].keys()) == {"wb-global", "wb-session", "wb-idle"}
    active = wbi.list_active_worldbook_ids("chat-1", set())
    assert set(active) == {"wb-global", "wb-session"}
    active_excl = wbi.list_active_worldbook_ids("chat-1", {"wb-global"})
    assert set(active_excl) == {"wb-session"}


def test_collect_active_worldbooks_loads_only_active(monkeypatch, tmp_path) -> None:
    _chats, books = _patch_data(monkeypatch, tmp_path)
    for i in range(20):
        _write_book(books, f"wb-{i:02d}", global_active=(i < 2))
    wbi.rebuild_worldbook_index()

    load_calls: list[str] = []
    real_load = storage.load_worldbook

    def counting(wid: str):
        load_calls.append(wid)
        return real_load(wid)

    monkeypatch.setattr(gen, "load_worldbook", counting)
    active = gen.collect_active_worldbooks("chat-x", None, set())
    assert len(active) == 2
    assert len(load_calls) == 2


def test_ensure_mvu_worker_reuses_loaded_chat_and_character() -> None:
    chat = Chat(id="reuse-chat", characterId="char-r", title="t", messages=[])
    character = type("C", (), {"id": "char-r", "name": "R"})()
    mvu_daemon._health.pop(chat.id, None)
    mvu_daemon._tasks.pop(chat.id, None)

    with patch("app.services.mvu_daemon.load_chat") as load_chat:
        with patch("app.services.mvu_daemon.load_character") as load_character:
            with patch(
                "app.services.mvu_daemon.resolve_chat_mvu_runtime_enablement",
                return_value=type("E", (), {"enabled": False, "character_error": None})(),
            ):
                ok = mvu_daemon.ensure_mvu_worker(chat.id, chat=chat, character=character)
    assert ok is False
    load_chat.assert_not_called()
    load_character.assert_not_called()


def test_prepare_reuses_match_when_scan_scope_unchanged(monkeypatch, tmp_path) -> None:
    _chats, books = _patch_data(monkeypatch, tmp_path)
    _write_book(books, "wb-a", global_active=True)
    wbi.rebuild_worldbook_index()

    chat = Chat(
        id="prep-chat",
        characterId="char-a",
        title="t",
        overrides=ChatOverrides(),
        messages=[],
    )
    settings = Settings()
    conversation = [
        {"role": "user", "content": f"msg {i} keyword"} for i in range(30)
    ]
    # 足够大的 context，二次 trim 通常不会改动扫描尾部
    out, warnings, profile = gen.prepare_conversation_with_worldbooks(
        conversation=conversation,
        chat=chat,
        settings=settings,
        system_prompt="system",
        context_size=100000,
    )
    assert isinstance(out, list)
    assert profile["counters"]["matchPass1"] >= 1
    assert profile["counters"]["matchReused"] >= 1
    assert profile["counters"]["matchPass2"] == 0
    assert "prepTotal" in profile["segmentsMs"]
    assert gen.get_last_generate_prep_profile() is not None


def test_prepare_worldbook_load_baseline(monkeypatch, tmp_path) -> None:
    _chats, books = _patch_data(monkeypatch, tmp_path)
    # 18 idle + 2 active
    for i in range(20):
        _write_book(books, f"base-{i:02d}", global_active=(i < 2))
    wbi.rebuild_worldbook_index()

    chat = Chat(id="base-chat", characterId="c", title="t", overrides=ChatOverrides(), messages=[])
    settings = Settings()
    conversation = [{"role": "user", "content": f"line {i} keyword"} for i in range(80)]

    t0 = time.perf_counter()
    _out, _w, profile = gen.prepare_conversation_with_worldbooks(
        conversation=conversation,
        chat=chat,
        settings=settings,
        system_prompt="sys " * 20,
        context_size=8000,
    )
    prep_ms = (time.perf_counter() - t0) * 1000
    assert profile["counters"]["worldbooksLoaded"] == 2
    assert prep_ms < 2000
    print(f"generate_prep_total_ms={profile['segmentsMs']['prepTotal']:.2f}")
    print(f"generate_prep_worldbook_load_ms={profile['segmentsMs']['worldbookLoad']:.2f}")
    print(f"generate_prep_match1_ms={profile['segmentsMs']['worldbookMatch1']:.2f}")
    print(f"generate_prep_match2_ms={profile['segmentsMs']['worldbookMatch2']:.2f}")
    print(f"generate_prep_match_reused={profile['counters']['matchReused']}")


def test_scan_scope_equivalent_helper() -> None:
    base = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    trimmed = [{"role": "assistant", "content": "b"}]
    assert gen._scan_scope_equivalent(base, trimmed, 1) is True
    assert gen._scan_scope_equivalent(base, trimmed, 2) is False
    assert gen._scan_scope_equivalent(base, trimmed, 0) is True
