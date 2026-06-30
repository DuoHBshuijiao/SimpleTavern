import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import CharacterCard, Chat, ChatOverrides, CreateChatRequest, UpdateChatRequest
from app.routes.chats import _merge_overrides, create_chat


class MvuDirectiveFoundationTests(unittest.TestCase):
    def test_legacy_character_defaults_to_regex_mode(self) -> None:
        card = CharacterCard.model_validate({"id": "char_legacy", "name": "旧角色"})

        self.assertEqual(card.mvuMode, "regex")
        self.assertIsNone(card.mvuDirective)

    def test_single_chat_inherits_directive_mode_from_character(self) -> None:
        character = CharacterCard(
            id="char_directive",
            name="指令角色",
            mvuMode="directive",
            mvuDirective="按指令更新状态",
        )

        with (
            patch("app.routes.chats.load_character", return_value=character),
            patch("app.routes.chats.load_settings", side_effect=FileNotFoundError),
            patch("app.routes.chats.save_chat", side_effect=lambda chat: chat),
        ):
            chat = create_chat(CreateChatRequest(characterId=character.id))

        self.assertEqual(chat.overrides.mvuMode, "directive")
        self.assertEqual(chat.overrides.mvuDirective, "按指令更新状态")

    def test_merge_overrides_only_updates_explicit_mvu_fields(self) -> None:
        chat = Chat(characterId="char_1")
        chat.overrides.mvuMode = "directive"
        chat.overrides.mvuDirective = "保留旧指令"

        _merge_overrides(chat, UpdateChatRequest(overrides=ChatOverrides(prompt="只改提示词")))

        self.assertEqual(chat.overrides.mvuMode, "directive")
        self.assertEqual(chat.overrides.mvuDirective, "保留旧指令")

        _merge_overrides(
            chat,
            UpdateChatRequest(
                overrides=ChatOverrides(
                    mvuMode="regex",
                    mvuDirective="   ",
                ),
            ),
        )

        self.assertEqual(chat.overrides.mvuMode, "regex")
        self.assertIsNone(chat.overrides.mvuDirective)


if __name__ == "__main__":
    unittest.main()
