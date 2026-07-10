from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import Mock

from app import fork_index as fi
from app.errors import AppError
from app.schemas import Chat, ChatMessage


def _patch_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    chats = data / "chats"
    chats.mkdir(parents=True)
    index_path = data / "fork_index.json"
    monkeypatch.setattr(fi, "_fork_index_path", lambda: index_path)
    monkeypatch.setattr(fi, "_chats_dir", lambda: chats)
    fi._pending_warnings.clear()
    fi._index_dirty = False
    return chats, index_path


def _write_chat(chats: Path, chat: Chat) -> None:
    path = chats / chat.characterId / chat.id / "chat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(chat.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )


def _fork_pair(chats: Path) -> tuple[Chat, Chat]:
    parent = Chat(
        id="parent",
        characterId="char-1",
        title="Parent",
        messages=[ChatMessage(id="message-1", role="user", content="hello")],
    )
    child = Chat(
        id="child",
        characterId="char-1",
        title="Child",
        messages=[ChatMessage(id="message-1", role="user", content="hello")],
        forkedFromChatId=parent.id,
        forkedFromMessageId="message-1",
        forkedFromMessageIndex=1,
    )
    _write_chat(chats, parent)
    _write_chat(chats, child)
    return parent, child


def test_corrupt_index_rebuilds_and_returns_visible_warning(
    monkeypatch,
    tmp_path,
) -> None:
    chats, index_path = _patch_paths(monkeypatch, tmp_path)
    parent, child = _fork_pair(chats)
    index_path.write_text("{broken", encoding="utf-8")

    lineage = fi.build_fork_lineage(child.id)

    assert lineage.origin is not None
    assert lineage.origin.chatId == parent.id
    assert lineage.partialSuccess is True
    assert [warning.code for warning in lineage.warnings] == ["fork_index_corrupt"]
    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
    assert rebuilt["rebuilt"] is True
    assert child.id in rebuilt["byChild"]


def test_sync_after_corruption_does_not_poison_index_with_partial_state(
    monkeypatch,
    tmp_path,
) -> None:
    chats, index_path = _patch_paths(monkeypatch, tmp_path)
    _parent, child = _fork_pair(chats)
    index_path.write_text("{broken", encoding="utf-8")
    child.title = "Updated child"

    fi.sync_chat_fork_index(child)

    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
    assert rebuilt["rebuilt"] is True
    assert child.id in rebuilt["byChild"]
    assert rebuilt["titles"][child.id] == "Updated child"
    lineage = fi.build_fork_lineage(child.id)
    assert any(warning.code == "fork_index_corrupt" for warning in lineage.warnings)


def test_lineage_rebuild_failure_is_structured_and_retryable(
    monkeypatch,
    tmp_path,
) -> None:
    _chats, index_path = _patch_paths(monkeypatch, tmp_path)
    index_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(
        fi,
        "rebuild_fork_index",
        Mock(side_effect=OSError("disk read-only")),
    )

    try:
        fi.build_fork_lineage("chat-1")
    except AppError as error:
        assert error.code == "fork_index_rebuild_failed"
        assert error.status_code == 503
        assert error.retryable is True
    else:
        raise AssertionError("expected AppError")


def test_rebuild_uses_lightweight_metadata_when_anchor_index_exists(
    monkeypatch,
    tmp_path,
) -> None:
    chats, _index_path = _patch_paths(monkeypatch, tmp_path)
    _fork_pair(chats)
    load_chat = Mock(side_effect=AssertionError("full chat load is not expected"))
    monkeypatch.setattr(fi, "load_chat", load_chat)

    fi.rebuild_fork_index()

    load_chat.assert_not_called()


def test_sync_failure_marks_index_dirty_and_next_lineage_rebuilds(
    monkeypatch,
    tmp_path,
) -> None:
    chats, _index_path = _patch_paths(monkeypatch, tmp_path)
    _parent, child = _fork_pair(chats)
    fi.rebuild_fork_index()
    original_save = fi._save_index_unlocked
    calls = 0

    def fail_once(data):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("write failed")
        original_save(data)

    monkeypatch.setattr(fi, "_save_index_unlocked", fail_once)
    fi.sync_chat_fork_index(child)
    assert fi._index_dirty is True

    lineage = fi.build_fork_lineage(child.id)

    assert fi._index_dirty is False
    assert lineage.origin is not None
    assert any(warning.code == "fork_index_sync_failed" for warning in lineage.warnings)


def test_unreadable_fork_meta_warning_remains_sticky(
    monkeypatch,
    tmp_path,
) -> None:
    chats, _index_path = _patch_paths(monkeypatch, tmp_path)
    record = chats / "char-1" / "chat-1" / "chat.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fi, "read_chat_fork_meta", Mock(return_value=None))

    first = fi.build_fork_lineage("chat-1")
    second = fi.build_fork_lineage("chat-1")

    assert any(warning.code == "fork_meta_unreadable" for warning in first.warnings)
    assert any(warning.code == "fork_meta_unreadable" for warning in second.warnings)


def test_rebuild_1000_chat_lightweight_baseline(
    monkeypatch,
    tmp_path,
) -> None:
    chats, index_path = _patch_paths(monkeypatch, tmp_path)
    character_dir = chats / "char-1"
    for index in range(1000):
        chat_id = f"chat-{index:04d}"
        path = character_dir / chat_id / "chat.json"
        path.parent.mkdir(parents=True)
        is_fork = index > 0 and index % 10 == 0
        path.write_text(
            json.dumps(
                {
                    "id": chat_id,
                    "title": chat_id,
                    "createdAt": "2026-07-10T00:00:00+00:00",
                    "messages": [],
                    "forkedFromChatId": "chat-0000" if is_fork else None,
                    "forkedFromMessageId": "message-1" if is_fork else None,
                    "forkedFromMessageIndex": 1 if is_fork else None,
                }
            ),
            encoding="utf-8",
        )

    started = time.perf_counter()
    fi.rebuild_fork_index()
    duration_ms = (time.perf_counter() - started) * 1000
    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))

    assert len(rebuilt["byChild"]) == 99
    assert duration_ms < 5000
    print(f"fork_index_rebuild_1000_chat_ms={duration_ms:.2f}")
