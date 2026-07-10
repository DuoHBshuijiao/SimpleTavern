from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

from app import storage
from app.errors import AppError
from app.request_context import _request_id_var
from app.routes import update as update_route
from app.schemas import Chat, ChatImageAttachment, ChatMessage
from app.services.cleanup_log import log_cleanup_failure
from app.services.data_integrity import data_integrity_service


def _patch_storage_dirs(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    data = tmp_path / "data"
    characters = data / "characters"
    worldbooks = data / "worldbooks"
    chats = data / "chats"
    for directory in (characters, worldbooks, chats):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "_data_dir", lambda: data)
    monkeypatch.setattr(storage, "_characters_dir", lambda: characters)
    monkeypatch.setattr(storage, "_worldbooks_dir", lambda: worldbooks)
    monkeypatch.setattr(storage, "_chats_dir", lambda: chats)
    return characters, worldbooks, chats


def test_character_and_worldbook_lists_keep_good_items_and_report_corruption(
    monkeypatch,
    tmp_path,
) -> None:
    characters, worldbooks, _chats = _patch_storage_dirs(monkeypatch, tmp_path)
    (characters / "good.json").write_text(
        json.dumps({"id": "good", "name": "Good"}),
        encoding="utf-8",
    )
    (characters / "broken.json").write_text("{broken", encoding="utf-8")
    (worldbooks / "good-book.json").write_text(
        json.dumps({"id": "good-book", "name": "Good Book"}),
        encoding="utf-8",
    )
    (worldbooks / "broken-book.json").write_text(
        json.dumps({"id": "broken-book"}),
        encoding="utf-8",
    )
    report = Mock()
    clear = Mock()

    with (
        patch.object(data_integrity_service, "record_runtime_failure", report),
        patch.object(data_integrity_service, "clear_runtime_issue", clear),
    ):
        cards = storage.list_characters()
        books = storage.list_worldbooks()

    assert [card.id for card in cards] == ["good"]
    assert [book.id for book in books] == ["good-book"]
    reported = {(call.args[0].name, call.args[1]) for call in report.call_args_list}
    assert reported == {
        ("broken.json", "character_card"),
        ("broken-book.json", "world_book"),
    }
    assert {call.args[0].name for call in clear.call_args_list} == {
        "good.json",
        "good-book.json",
    }


def test_loading_corrupt_character_is_not_reported_as_not_found(
    monkeypatch,
    tmp_path,
) -> None:
    characters, _worldbooks, _chats = _patch_storage_dirs(monkeypatch, tmp_path)
    path = characters / "broken.json"
    path.write_text(json.dumps({"name": "Missing id"}), encoding="utf-8")
    report = Mock()

    with patch.object(data_integrity_service, "record_runtime_failure", report):
        try:
            storage.load_character("broken")
        except AppError as error:
            assert error.code == "data_corrupted"
            assert error.source == "storage.character"
        else:
            raise AssertionError("expected AppError")

    assert report.call_args.args[0] == path
    assert report.call_args.args[1] == "character_card"


def test_loading_corrupt_chat_is_not_reported_as_not_found(
    monkeypatch,
    tmp_path,
) -> None:
    _characters, _worldbooks, chats = _patch_storage_dirs(monkeypatch, tmp_path)
    path = chats / "char-1" / "chat-1" / storage.CHAT_RECORD_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    report = Mock()

    with patch.object(data_integrity_service, "record_runtime_failure", report):
        try:
            storage.load_chat("chat-1")
        except AppError as error:
            assert error.code == "data_corrupted"
            assert error.source == "storage.chat"
        else:
            raise AssertionError("expected AppError")

    assert report.call_args.args[0] == path
    assert report.call_args.args[1] == "chat_record"

    try:
        storage.load_chat("missing")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_corrupt_update_ignore_is_not_overwritten(
    monkeypatch,
    tmp_path,
) -> None:
    _patch_storage_dirs(monkeypatch, tmp_path)
    path = storage.update_ignore_path()
    original = "{broken"
    path.write_text(original, encoding="utf-8")

    try:
        storage.load_update_ignore()
    except AppError as error:
        assert error.code == "update_ignore_corrupt"
    else:
        raise AssertionError("expected AppError")

    assert path.read_text(encoding="utf-8") == original


def test_startup_update_check_preserves_update_ignore_app_error() -> None:
    expected = AppError(
        code="update_ignore_corrupt",
        message="更新忽略配置已损坏",
        source="storage.update_ignore",
        status_code=500,
    )
    with (
        patch.object(update_route, "_fetch_latest_release", return_value={}),
        patch.object(update_route, "_build_update_payload", return_value={}),
        patch.object(update_route, "_load_ignored_release_tag", side_effect=expected),
    ):
        try:
            update_route.startup_check_update()
        except AppError as error:
            assert error is expected
        else:
            raise AssertionError("expected AppError")


def test_cleanup_failure_log_contains_request_id(caplog) -> None:
    token = _request_id_var.set("req_cleanup_123")
    try:
        with caplog.at_level(logging.WARNING, logger="app.services.cleanup_log"):
            log_cleanup_failure(
                source="test.cleanup",
                exc=OSError("cannot remove"),
                path="data/example",
            )
    finally:
        _request_id_var.reset(token)

    assert "cleanup_failed" in caplog.text
    assert "req_cleanup_123" in caplog.text
    assert "test.cleanup" in caplog.text


def test_delete_message_images_logs_cleanup_and_keeps_main_flow(
    monkeypatch,
    caplog,
) -> None:
    chat = Chat(id="chat-1", characterId="char-1")
    message = ChatMessage(
        role="user",
        content="hello",
        images=[
            ChatImageAttachment(
                id="image-1",
                filename="image.png",
                mimeType="image/png",
                size=1,
            )
        ],
    )
    monkeypatch.setattr(
        storage,
        "delete_chat_image",
        Mock(side_effect=OSError("locked")),
    )

    with caplog.at_level(logging.WARNING, logger="app.services.cleanup_log"):
        storage.delete_message_images(chat, message)

    assert "storage.delete_message_images" in caplog.text


def test_rmtree_best_effort_logs_each_callback_failure(
    monkeypatch,
    caplog,
    tmp_path,
) -> None:
    target = tmp_path / "cleanup"
    target.mkdir()

    def fake_rmtree(_target, *, onerror):
        first = OSError("first locked file")
        second = OSError("second locked file")
        onerror(None, str(target / "first"), (OSError, first, None))
        onerror(None, str(target / "second"), (OSError, second, None))

    monkeypatch.setattr(storage.shutil, "rmtree", fake_rmtree)
    with caplog.at_level(logging.WARNING, logger="app.services.cleanup_log"):
        storage._rmtree_best_effort(target, source="test.rmtree")

    assert caplog.text.count("cleanup_failed") == 2
    assert "first" in caplog.text
    assert "second" in caplog.text
