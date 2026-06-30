"""正文正则 CRUD 工具单测（mock 存储）。"""
import unittest
from unittest.mock import patch

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.handlers.content_regex_tools import (
    handle_character_content_regex_manage,
    handle_chat_content_regex_manage,
)
from app.schemas import AssistantSettings, Chat, ChatOverrides, CharacterCard


def _ctx(chat_id: str) -> AssistantToolContext:
    return AssistantToolContext(
        chat_id=chat_id,
        scope=None,
        allow_write_memory=False,
        allow_destructive_tools=False,
        assistant_settings=AssistantSettings(),
    )


class TestChatContentRegexManage(unittest.TestCase):
    def test_list_empty(self) -> None:
        chat = Chat(characterId="c1", overrides=ChatOverrides())
        with patch("app.assistant_tools.handlers.content_regex_tools.load_chat", return_value=chat):
            r = handle_chat_content_regex_manage(_ctx("x"), {"operation": "list"})
        self.assertTrue(r.get("ok"))
        self.assertEqual(r.get("data", {}).get("count"), 0)

    def test_upsert_and_delete_session_rule(self) -> None:
        chat = Chat(characterId="c1", overrides=ChatOverrides())
        with patch("app.assistant_tools.handlers.content_regex_tools.load_chat", return_value=chat):
            with patch("app.assistant_tools.handlers.content_regex_tools.save_chat") as m_save:
                r1 = handle_chat_content_regex_manage(
                    _ctx("x"),
                    {
                        "operation": "upsert",
                        "rule": {"name": "隐藏 UV", "pattern": "(?s)<UpdateVariable>.*?</UpdateVariable>", "action": "remove"},
                    },
                )
        self.assertTrue(r1.get("ok"))
        rules = r1.get("data", {}).get("rules") or []
        self.assertEqual(len(rules), 1)
        rid = rules[0]["id"]
        m_save.assert_called_once()

        with patch("app.assistant_tools.handlers.content_regex_tools.load_chat", return_value=chat):
            with patch("app.assistant_tools.handlers.content_regex_tools.save_chat"):
                r2 = handle_chat_content_regex_manage(_ctx("x"), {"operation": "delete", "rule_id": rid})
        self.assertTrue(r2.get("ok"))
        self.assertEqual(len(chat.overrides.contentRegexRules), 0)


class TestCharacterContentRegexManage(unittest.TestCase):
    def test_upsert_character_rule(self) -> None:
        chat = Chat(characterId="char99", overrides=ChatOverrides())
        card = CharacterCard(id="char99", name="t")
        with patch("app.assistant_tools.handlers.content_regex_tools.load_chat", return_value=chat):
            with patch("app.assistant_tools.handlers.content_regex_tools.load_character", return_value=card):
                with patch("app.assistant_tools.handlers.content_regex_tools.save_character") as m_save:
                    r = handle_character_content_regex_manage(
                        _ctx("x"),
                        {
                            "operation": "upsert",
                            "rule": {"name": "r1", "pattern": "foo", "action": "remove"},
                        },
                    )
        self.assertTrue(r.get("ok"))
        self.assertEqual(len(card.contentRegexRules), 1)
        m_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
