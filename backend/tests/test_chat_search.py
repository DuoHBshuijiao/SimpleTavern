import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import chats


def _chat(count: int):
    messages = [SimpleNamespace(id=f"m{i}", content="含有关键词的消息") for i in range(count)]
    return SimpleNamespace(messages=messages)


class ChatSearchLimitTest(unittest.TestCase):
    def _search(self, count: int):
        with patch.object(chats, "load_chat", return_value=_chat(count)):
            return chats.search_chat("chat", q="关键词")

    def test_exactly_at_limit_is_not_truncated(self):
        res = self._search(chats.CHAT_SEARCH_HIT_LIMIT)
        self.assertEqual(res.total, chats.CHAT_SEARCH_HIT_LIMIT)
        self.assertFalse(res.truncated)

    def test_over_limit_keeps_first_hits_and_reports_truncated(self):
        res = self._search(chats.CHAT_SEARCH_HIT_LIMIT + 1)
        self.assertEqual(len(res.hits), chats.CHAT_SEARCH_HIT_LIMIT)
        self.assertEqual(res.hits[0].messageId, "m0")
        self.assertTrue(res.truncated)


if __name__ == "__main__":
    unittest.main()
