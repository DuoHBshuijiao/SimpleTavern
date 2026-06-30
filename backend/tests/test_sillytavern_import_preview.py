from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import StatusTableDef  # noqa: E402
from app.routes import import_export as ie  # noqa: E402
from app.services.st_mvu_compat import build_regex_compat_result  # noqa: E402


def _png_with_chara_payload(raw: dict) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return len(data).to_bytes(4, "big") + kind + data + crc.to_bytes(4, "big")

    encoded = base64.b64encode(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
    text_data = b"chara\x00" + encoded
    return b"\x89PNG\r\n\x1a\n" + chunk(b"tEXt", text_data) + chunk(b"IEND", b"")


def _mvu_st_card() -> dict:
    return {
        "spec": "chara_card_v3",
        "data": {
            "name": "MVU Hero",
            "description": "desc",
            "first_mes": "hello",
            "extensions": {
                "tavern_helper": {"enabled": True},
                "regex_scripts": [
                    {
                        "scriptName": "隐藏变量更新",
                        "findRegex": r"<UpdateVariable>([\s\S]*?)</UpdateVariable>",
                        "replaceString": "",
                    },
                ],
            },
            "character_book": {
                "name": "MVU Book",
                "entries": [
                    {
                        "comment": "MVU 状态栏",
                        "content": "更新状态变量",
                        "keys": ["状态"],
                        "enabled": True,
                    },
                    {"comment": "普通世界观", "content": "lore", "keys": ["lore"]},
                ],
            },
        },
    }


class SillyTavernImportPreviewTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        if hasattr(ie, "_sillytavern_pending_store"):
            ie._sillytavern_pending_store.clear()

    async def test_preview_png_detects_mvu_without_writing(self) -> None:
        file = UploadFile(filename="title.png", file=io.BytesIO(_png_with_chara_payload(_mvu_st_card())))

        with (
            patch.object(ie, "save_character", side_effect=AssertionError("preview must not save character")),
            patch.object(ie, "save_worldbook", side_effect=AssertionError("preview must not save worldbook")),
            patch.object(ie, "save_avatar", side_effect=AssertionError("preview must not save avatar")),
        ):
            result = await ie.preview_sillytavern_import(file)

        self.assertTrue(result["ok"])
        self.assertTrue(result["pendingId"])
        preview = result["preview"]
        self.assertEqual(preview["characterName"], "MVU Hero")
        self.assertEqual(preview["worldBookName"], "MVU Book")
        self.assertEqual(preview["worldBookEntryCount"], 2)
        self.assertTrue(preview["mvu"]["hasTavernHelper"])
        self.assertTrue(preview["mvu"]["hasRegexScripts"])
        self.assertEqual(preview["mvu"]["regexScriptCount"], 1)
        self.assertEqual(preview["mvu"]["characterBookCandidateCount"], 1)

    async def test_confirm_regex_mvu_compat_writes_back_content_regex_rules(self) -> None:
        preview = await ie.preview_sillytavern_import(
            UploadFile(filename="title.png", file=io.BytesIO(_png_with_chara_payload(_mvu_st_card()))),
        )
        saved_cards = []
        saved_worldbooks = []
        saved_avatars = []

        def save_character_stub(card):
            saved_cards.append(card)
            return card

        def save_worldbook_stub(worldbook):
            saved_worldbooks.append(worldbook)
            return worldbook

        def save_avatar_stub(filename: str, payload: bytes):
            saved_avatars.append((filename, payload))

        with (
            patch.object(ie, "save_character", side_effect=save_character_stub),
            patch.object(ie, "save_worldbook", side_effect=save_worldbook_stub),
            patch.object(ie, "save_avatar", side_effect=save_avatar_stub),
        ):
            result = await ie.confirm_sillytavern_import(
                ie.SillyTavernConfirmRequest(
                    pendingId=preview["pendingId"],
                    enableMvuCompatibility=True,
                    mvuMode="regex",
                ),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["imported"], ["character", "worldbook"])
        self.assertEqual(len(saved_avatars), 1)
        self.assertEqual(len(saved_worldbooks), 1)
        self.assertEqual(len(saved_worldbooks[0].entries), 2)
        self.assertEqual(saved_worldbooks[0].entries[1].content, "lore")
        self.assertEqual(len(saved_cards), 1)
        final_saved = saved_cards[0]
        self.assertEqual(final_saved.attachedWorldBookIds, [saved_worldbooks[0].id])
        self.assertTrue(final_saved.mvuEnabled)
        self.assertEqual(final_saved.mvuMode, "regex")
        self.assertIsNone(final_saved.mvuDirective)
        self.assertEqual(len(final_saved.contentRegexRules), 1)
        self.assertEqual(final_saved.contentRegexRules[0].action, "remove")
        self.assertIn("UpdateVariable", final_saved.contentRegexRules[0].pattern)
        self.assertEqual(result["mvu"]["requestedMode"], "regex")
        self.assertTrue(result["mvu"]["enabled"])
        self.assertEqual(result["mvuCompat"]["mode"], "regex")
        self.assertTrue(result["mvuCompat"]["applied"])
        self.assertEqual(result["mvuCompat"]["rules"], 1)

        with self.assertRaises(HTTPException):
            await ie.confirm_sillytavern_import(
                ie.SillyTavernConfirmRequest(
                    pendingId=preview["pendingId"],
                    enableMvuCompatibility=True,
                    mvuMode="regex",
                ),
            )

    def test_regex_compat_generates_hidden_update_variable_rule(self) -> None:
        result = build_regex_compat_result(_mvu_st_card())

        self.assertEqual(result["mode"], "regex")
        self.assertTrue(result["applied"])
        self.assertEqual(len(result["regexRules"]), 1)
        rule = result["regexRules"][0]
        self.assertEqual(rule["action"], "remove")
        self.assertIn("UpdateVariable", rule["pattern"])
        self.assertEqual(result["summary"], "生成 regex 兼容规则 1 条。")

    def test_regex_compat_warns_and_skips_large_html_ui_rule(self) -> None:
        raw = _mvu_st_card()
        raw["data"]["extensions"]["regex_scripts"] = [
            {
                "scriptName": "复杂 UI",
                "findRegex": r"<div class=\"panel\">([\s\S]*?)</div>",
                "replaceString": "<style>.panel{color:red}</style><div><button onclick=\"doThing()\">更新</button></div>" * 40,
            },
        ]

        result = build_regex_compat_result(raw)

        self.assertFalse(result["applied"])
        self.assertEqual(result["regexRules"], [])
        self.assertIn("不可表达", "; ".join(result["warnings"]))

    async def test_confirm_regex_mvu_compat_failure_keeps_imported_character_and_warns(self) -> None:
        preview = await ie.preview_sillytavern_import(
            UploadFile(filename="title.png", file=io.BytesIO(_png_with_chara_payload(_mvu_st_card()))),
        )
        saved_cards = []
        saved_worldbooks = []

        def save_character_stub(card):
            saved_cards.append(card.model_copy(deep=True))
            return card

        def save_worldbook_stub(worldbook):
            saved_worldbooks.append(worldbook.model_copy(deep=True))
            return worldbook

        with (
            patch.object(ie, "save_character", side_effect=save_character_stub),
            patch.object(ie, "save_worldbook", side_effect=save_worldbook_stub),
            patch.object(ie, "save_avatar", return_value=None),
            patch.object(ie, "run_st_mvu_regex_compat_agent", side_effect=RuntimeError("regex analyzer offline")),
        ):
            result = await ie.confirm_sillytavern_import(
                ie.SillyTavernConfirmRequest(
                    pendingId=preview["pendingId"],
                    enableMvuCompatibility=True,
                    mvuMode="regex",
                ),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["imported"], ["character", "worldbook"])
        self.assertEqual(len(saved_cards), 1)
        self.assertEqual(saved_cards[0].attachedWorldBookIds, [saved_worldbooks[0].id])
        self.assertTrue(saved_cards[0].mvuEnabled)
        self.assertEqual(saved_cards[0].mvuMode, "regex")
        self.assertEqual(saved_cards[0].contentRegexRules, [])
        self.assertFalse(result["mvuCompat"]["applied"])
        self.assertIn("regex analyzer offline", "; ".join(result["mvuCompat"]["warnings"]))

    async def test_confirm_directive_mvu_compat_writes_back_character_fields_and_keeps_worldbook(self) -> None:
        preview = await ie.preview_sillytavern_import(
            UploadFile(filename="title.png", file=io.BytesIO(_png_with_chara_payload(_mvu_st_card()))),
        )
        saved_cards = []
        saved_worldbooks = []
        agent_calls = []
        agent_result = {
            "mode": "directive",
            "applied": True,
            "directive": "根据状态栏更新生命值与位置。",
            "summary": "MVU Agent 已生成 1 张初始状态表。",
            "initialStateTables": [
                {
                    "name": "角色状态",
                    "columns": ["当前值"],
                    "rows": [{"field": "生命值", "cells": {"当前值": "100"}}],
                },
            ],
            "worldbookMarks": [{"title": "MVU 状态栏", "reason": "状态候选"}],
            "warnings": ["复杂 UI regex_scripts 已作为 MVU 语义线索处理，未生成正文正则规则。"],
            "confidence": 0.81,
        }

        async def run_import_agent_stub(raw):
            agent_calls.append(raw)
            return agent_result

        def save_character_stub(card):
            saved_cards.append(card.model_copy(deep=True))
            return card

        def save_worldbook_stub(worldbook):
            saved_worldbooks.append(worldbook.model_copy(deep=True))
            return worldbook

        with (
            patch.object(ie, "save_character", side_effect=save_character_stub),
            patch.object(ie, "save_worldbook", side_effect=save_worldbook_stub),
            patch.object(ie, "save_avatar", return_value=None),
            patch.object(ie, "run_st_mvu_import_agent", side_effect=run_import_agent_stub),
        ):
            result = await ie.confirm_sillytavern_import(
                ie.SillyTavernConfirmRequest(
                    pendingId=preview["pendingId"],
                    enableMvuCompatibility=True,
                    mvuMode="directive",
                ),
            )

        self.assertEqual(len(saved_worldbooks), 1)
        self.assertEqual(len(saved_cards), 1)
        final_saved = saved_cards[0]
        self.assertEqual(final_saved.attachedWorldBookIds, [saved_worldbooks[0].id])
        self.assertTrue(final_saved.mvuEnabled)
        self.assertEqual(final_saved.mvuMode, "directive")
        self.assertEqual(final_saved.mvuDirective, "根据状态栏更新生命值与位置。")
        self.assertEqual(
            [table.model_dump(mode="json") for table in final_saved.initialStateTables],
            [StatusTableDef.model_validate(agent_result["initialStateTables"][0]).model_dump(mode="json")],
        )
        self.assertEqual(result["mvuCompat"]["mode"], "directive")
        self.assertTrue(result["mvuCompat"]["applied"])
        self.assertEqual(result["mvuCompat"]["summary"], "MVU Agent 已生成 1 张初始状态表。")
        self.assertEqual(result["mvuCompat"]["worldbookMarks"], agent_result["worldbookMarks"])
        self.assertIn("复杂 UI regex_scripts", result["warnings"][0])
        self.assertEqual(len(saved_worldbooks[0].entries), 2)
        self.assertEqual(saved_worldbooks[0].entries[0].enabled, True)
        self.assertEqual(saved_worldbooks[0].entries[1].content, "lore")
        self.assertEqual(len(agent_calls), 1)
        self.assertEqual(agent_calls[0]["data"]["extensions"]["regex_scripts"][0]["findRegex"], r"<UpdateVariable>([\s\S]*?)</UpdateVariable>")
        self.assertEqual(agent_calls[0]["data"]["character_book"]["entries"][1]["content"], "lore")

    async def test_confirm_directive_mvu_compat_failure_keeps_imported_character_and_warns(self) -> None:
        preview = await ie.preview_sillytavern_import(
            UploadFile(filename="title.png", file=io.BytesIO(_png_with_chara_payload(_mvu_st_card()))),
        )
        saved_cards = []
        saved_worldbooks = []

        def save_character_stub(card):
            saved_cards.append(card.model_copy(deep=True))
            return card

        def save_worldbook_stub(worldbook):
            saved_worldbooks.append(worldbook.model_copy(deep=True))
            return worldbook

        with (
            patch.object(ie, "save_character", side_effect=save_character_stub),
            patch.object(ie, "save_worldbook", side_effect=save_worldbook_stub),
            patch.object(ie, "save_avatar", return_value=None),
            patch.object(ie, "run_st_mvu_import_agent", side_effect=RuntimeError("agent offline")),
        ):
            result = await ie.confirm_sillytavern_import(
                ie.SillyTavernConfirmRequest(
                    pendingId=preview["pendingId"],
                    enableMvuCompatibility=True,
                    mvuMode="directive",
                ),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["imported"], ["character", "worldbook"])
        self.assertEqual(len(saved_cards), 1)
        self.assertEqual(saved_cards[0].attachedWorldBookIds, [saved_worldbooks[0].id])
        self.assertTrue(saved_cards[0].mvuEnabled)
        self.assertEqual(saved_cards[0].mvuMode, "directive")
        self.assertIsNone(saved_cards[0].mvuDirective)
        self.assertEqual(saved_cards[0].initialStateTables, [])
        self.assertFalse(result["mvuCompat"]["applied"])
        self.assertIn("agent offline", "; ".join(result["mvuCompat"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
