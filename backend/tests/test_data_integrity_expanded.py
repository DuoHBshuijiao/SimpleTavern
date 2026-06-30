"""Tests for expanded data integrity scanning: settings/characters/worldbooks + orphan references."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.services import data_integrity as di
from app.services.data_integrity import (
    DataIntegrityService,
    ScanTarget,
    _effective_repair_action,
)


def _patch_paths(monkeypatch, tmp_path: Path):
    data = tmp_path / "data"
    chars = data / "characters"
    wbs = data / "worldbooks"
    chats = data / "chats"
    for d in (chars, wbs, chats):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(di, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(di, "settings_path", lambda: data / "settings.json")
    monkeypatch.setattr(di, "assistant_settings_path", lambda: data / "assistant_settings.json")
    monkeypatch.setattr(di, "characters_dir", lambda: chars)
    monkeypatch.setattr(di, "worldbooks_dir", lambda: wbs)
    monkeypatch.setattr(di, "chats_dir", lambda: chats)
    monkeypatch.setattr(di, "assistant_chat_path", lambda: data / "assistant_chat.json")
    monkeypatch.setattr(di, "assistant_workspace_chat_path", lambda: data / "assistant_workspace_chat.json")
    return data, chars, wbs, chats


def test_effective_repair_action_protects_high_value_data():
    assert _effective_repair_action("chat_record", "invalid_json") == "delete"
    assert _effective_repair_action("assistant_chat_global", "empty") == "reset_json"
    assert _effective_repair_action("settings", "invalid_json") == "none"
    assert _effective_repair_action("assistant_settings", "empty") == "none"
    assert _effective_repair_action("character_card", "schema_mismatch") == "none"
    assert _effective_repair_action("world_book", "empty") == "none"
    # 孤儿引用所在的 chat 文件本身完好，绝不能按 chat_record 的 delete 自动删除
    assert _effective_repair_action("chat_record", "orphan_reference") == "none"
    assert _effective_repair_action("legacy_chat", "orphan_reference") == "none"


def test_validate_schema_for_new_kinds():
    svc = DataIntegrityService()

    settings_t = ScanTarget(path=Path("settings.json"), kind="settings")
    assert svc._validate_schema(settings_t, {"a": 1}) is None
    assert svc._validate_schema(settings_t, [1, 2]) is not None

    char_t = ScanTarget(path=Path("c.json"), kind="character_card")
    assert svc._validate_schema(char_t, {"id": "x", "name": "n"}) is None
    assert svc._validate_schema(char_t, {"name": "n"}) is not None  # 缺 id
    assert svc._validate_schema(char_t, "str") is not None

    wb_t = ScanTarget(path=Path("w.json"), kind="world_book")
    assert svc._validate_schema(wb_t, {"id": "w1"}) is None
    assert svc._validate_schema(wb_t, {}) is not None


def test_check_orphan_reference():
    svc = DataIntegrityService()
    chat_t = ScanTarget(path=Path("chat.json"), kind="chat_record")
    valid = {"hero"}
    assert svc._check_orphan_reference(chat_t, {"characterId": "hero"}, valid) is None
    orphan = svc._check_orphan_reference(chat_t, {"characterId": "ghost"}, valid)
    assert orphan is not None and orphan.code == "orphan_reference"
    # 无 valid set（如修复期重扫）不判定孤儿
    assert svc._check_orphan_reference(chat_t, {"characterId": "ghost"}, None) is None
    # 非会话类型不判定
    other = ScanTarget(path=Path("s.json"), kind="settings")
    assert svc._check_orphan_reference(other, {"characterId": "ghost"}, valid) is None


def test_enumerate_targets_includes_new_kinds(monkeypatch, tmp_path):
    data, chars, wbs, _chats = _patch_paths(monkeypatch, tmp_path)
    (data / "settings.json").write_text("{}", encoding="utf-8")
    (chars / "hero.json").write_text(json.dumps({"id": "hero", "name": "Hero"}), encoding="utf-8")
    (wbs / "wb1.json").write_text(json.dumps({"id": "wb1"}), encoding="utf-8")

    svc = DataIntegrityService()
    kinds = {t.kind for t in svc._enumerate_targets()}
    assert "settings" in kinds
    assert "character_card" in kinds
    assert "world_book" in kinds
    assert svc._collect_character_ids() == {"hero"}


def test_build_target_resolves_new_kinds(monkeypatch, tmp_path):
    data, chars, wbs, _chats = _patch_paths(monkeypatch, tmp_path)
    svc = DataIntegrityService()
    settings_t = svc._build_target(data / "settings.json")
    assert settings_t is not None and settings_t.kind == "settings"
    char_t = svc._build_target(chars / "hero.json")
    assert char_t is not None and char_t.kind == "character_card"
    wb_t = svc._build_target(wbs / "wb1.json")
    assert wb_t is not None and wb_t.kind == "world_book"


def test_scan_detects_orphan_and_corruption(monkeypatch, tmp_path):
    _data, chars, _wbs, chats = _patch_paths(monkeypatch, tmp_path)
    (chars / "hero.json").write_text(json.dumps({"id": "hero", "name": "Hero"}), encoding="utf-8")

    ghost_dir = chats / "ghost" / "c1"
    ghost_dir.mkdir(parents=True, exist_ok=True)
    ghost_chat = ghost_dir / "chat.json"
    ghost_chat.write_text(json.dumps({"id": "c1", "characterId": "ghost", "messages": []}), encoding="utf-8")

    broken = chars / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    svc = DataIntegrityService()
    valid = svc._collect_character_ids()  # {"hero", "broken"}：文件存在即视为角色存在

    chat_target = ScanTarget(path=ghost_chat.resolve(), kind="chat_record")
    result = asyncio.run(svc._scan_target(chat_target, valid))
    assert result is not None and result[1].code == "orphan_reference"

    char_target = ScanTarget(path=broken.resolve(), kind="character_card")
    corrupt = asyncio.run(svc._scan_target(char_target, valid))
    assert corrupt is not None and corrupt[1].code == "invalid_json"


def test_repair_skips_manual_kinds(monkeypatch, tmp_path):
    _data, chars, _wbs, _chats = _patch_paths(monkeypatch, tmp_path)
    broken = chars / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    svc = DataIntegrityService()

    async def _run():
        target = ScanTarget(path=broken.resolve(), kind="character_card")
        scan = await svc._scan_target(target)
        assert scan is not None
        await svc._upsert_issue(target, scan)
        return await svc.repair_issues()

    report = asyncio.run(_run())
    # 损坏角色卡只检测、不自动删除：仍存在于磁盘且被标记为 skipped
    assert broken.exists()
    assert report["repaired"] == []
    assert any("人工" in item.get("reason", "") for item in report["skipped"])


def test_list_issues_refreshes_stale_orphan(monkeypatch, tmp_path):
    _data, chars, _wbs, chats = _patch_paths(monkeypatch, tmp_path)

    ghost_dir = chats / "ghost" / "c1"
    ghost_dir.mkdir(parents=True, exist_ok=True)
    ghost_chat = ghost_dir / "chat.json"
    ghost_chat.write_text(json.dumps({"id": "c1", "characterId": "ghost", "messages": []}), encoding="utf-8")

    svc = DataIntegrityService()

    async def _run():
        target = ScanTarget(path=ghost_chat.resolve(), kind="chat_record")
        valid = svc._collect_character_ids()
        scan = await svc._scan_target(target, valid)
        assert scan is not None and scan[1].code == "orphan_reference"
        await svc._upsert_issue(target, scan)
        before = await svc.list_issues()
        assert before["hasIssues"] is True

        (chars / "ghost.json").write_text(
            json.dumps({"id": "ghost", "name": "Ghost"}), encoding="utf-8"
        )
        after = await svc.list_issues()
        return after

    report = asyncio.run(_run())
    assert report["hasIssues"] is False
    assert report["issues"] == []


def test_list_issues_refreshes_stale_corruption(monkeypatch, tmp_path):
    _data, chars, _wbs, _chats = _patch_paths(monkeypatch, tmp_path)
    broken = chars / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    svc = DataIntegrityService()

    async def _run():
        target = ScanTarget(path=broken.resolve(), kind="character_card")
        scan = await svc._scan_target(target)
        assert scan is not None and scan[1].code == "invalid_json"
        await svc._upsert_issue(target, scan)
        assert (await svc.list_issues())["hasIssues"] is True

        broken.write_text(json.dumps({"id": "broken", "name": "Fixed"}), encoding="utf-8")
        return await svc.list_issues()

    report = asyncio.run(_run())
    assert report["hasIssues"] is False
    assert report["issues"] == []


def test_repair_manual_kind_clears_cache_when_fixed(monkeypatch, tmp_path):
    _data, chars, _wbs, _chats = _patch_paths(monkeypatch, tmp_path)
    broken = chars / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    svc = DataIntegrityService()

    async def _run():
        target = ScanTarget(path=broken.resolve(), kind="character_card")
        scan = await svc._scan_target(target)
        await svc._upsert_issue(target, scan)
        broken.write_text(json.dumps({"id": "broken", "name": "Fixed"}), encoding="utf-8")
        return await svc.repair_issues()

    report = asyncio.run(_run())
    assert report["hasIssues"] is False
    assert report["remainingIssues"] == []
    assert report["skipped"] == []
