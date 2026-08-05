"""T-803-3B: chatId → path index."""

from __future__ import annotations

import json
import time
from pathlib import Path

import app.chat_path_index as cpi
import app.storage as storage


def _patch_paths(monkeypatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    chats = data / "chats"
    chats.mkdir(parents=True)
    monkeypatch.setattr(storage, "_data_dir", lambda: data)
    monkeypatch.setattr(storage, "_chats_dir", lambda: chats)
    # reset module state
    cpi._index_dirty = False
    cpi._memory_cache = None
    cpi._memory_mtime_ns = None
    return chats


def _make_chat(chats: Path, character_id: str, chat_id: str) -> Path:
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
                "messages": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_lookup_hits_index_after_rebuild(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    path = _make_chat(chats, "char-a", "chat-1")
    rebuilt = cpi.rebuild_chat_path_index()
    assert rebuilt["byId"]["chat-1"]["characterId"] == "char-a"
    found = storage._find_chat_path_by_id("chat-1")
    assert found is not None
    assert found[0] == path
    assert found[1] == "char-a"


def test_stale_index_entry_falls_back_to_scan(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    path = _make_chat(chats, "char-b", "chat-2")
    cpi.upsert_chat_path("chat-2", "missing-char", "folder")
    found = storage._find_chat_path_by_id("chat-2")
    assert found is not None
    assert found[0] == path
    assert found[1] == "char-b"
    # 回写后索引应纠正
    warm = cpi.warm_chat_path_index()
    assert warm["byId"]["chat-2"]["characterId"] == "char-b"


def test_save_chat_upserts_path_index(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("app.fork_index.sync_chat_fork_index", lambda _chat: None)
    monkeypatch.setattr("app.group_mvu.maybe_migrate_legacy_group_mvu_on_save", lambda _chat: None)
    from app.schemas import Chat

    chat = Chat(id="chat-new", characterId="char-c", title="t", messages=[])
    storage.save_chat(chat)
    warm = cpi.warm_chat_path_index()
    assert warm["byId"]["chat-new"]["characterId"] == "char-c"
    assert warm["byId"]["chat-new"]["format"] == "folder"
    assert (tmp_path / "data" / "chats" / "char-c" / "chat-new" / "chat.json").is_file()


def test_remove_chat_path_on_delete(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    _make_chat(chats, "char-d", "chat-del")
    cpi.rebuild_chat_path_index()
    assert "chat-del" in cpi.warm_chat_path_index()["byId"]
    storage.delete_chat("chat-del")
    assert "chat-del" not in cpi.warm_chat_path_index()["byId"]


def test_chat_path_rebuild_and_lookup_1000_baseline(monkeypatch, tmp_path) -> None:
    chats = _patch_paths(monkeypatch, tmp_path)
    chat_ids: list[str] = []
    # 50 角色 × 20 会话 = 1000，放大角色维度以体现索引收益
    for char_i in range(50):
        character_id = f"char-{char_i:02d}"
        for j in range(20):
            chat_id = f"chat-{char_i:02d}-{j:02d}"
            _make_chat(chats, character_id, chat_id)
            chat_ids.append(chat_id)

    started = time.perf_counter()
    rebuilt = cpi.rebuild_chat_path_index()
    rebuild_ms = (time.perf_counter() - started) * 1000
    assert len(rebuilt["byId"]) == 1000
    assert rebuild_ms < 1000
    print(f"chat_path_rebuild_1000_chat_ms={rebuild_ms:.2f}")

    # 暖索引：1000 次命中查找
    lookup_ms = cpi.measure_lookup_batch(chat_ids)
    assert lookup_ms < 500
    print(f"chat_path_lookup_1000_ms={lookup_ms:.2f}")
