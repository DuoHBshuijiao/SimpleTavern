import unittest

from app.routes import import_export


class JanitorImportTest(unittest.TestCase):
    def test_null_greetings_are_skipped_not_saved_as_none(self):
        card, _ = import_export._parse_character_from_json({
            "name": "Abelard",
            "first_messages": [None, "  ", "你好。"],
        })
        self.assertEqual(card.firstMessage, "你好。")
        self.assertEqual([e.text for e in card.extraFirstMessageEntries], [])

    def test_only_null_greeting_leaves_first_message_empty(self):
        card, _ = import_export._parse_character_from_json({"name": "Abelard", "first_messages": [None]})
        self.assertEqual(card.firstMessage, "")


if __name__ == "__main__":
    unittest.main()
