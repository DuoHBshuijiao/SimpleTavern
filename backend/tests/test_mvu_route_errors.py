from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routes.mvu import _load_chat_or_404


class TestMvuRouteErrors(unittest.TestCase):
    def test_empty_chat_id_fast_fails(self):
        with self.assertRaises(HTTPException) as ctx:
            _load_chat_or_404("  ")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "invalid_chat_id")
        self.assertIn("会话 ID", ctx.exception.detail["message"])

    @patch("app.routes.mvu.load_chat", side_effect=FileNotFoundError)
    def test_missing_chat_has_structured_detail(self, _load_chat):
        with self.assertRaises(HTTPException) as ctx:
            _load_chat_or_404("chat-missing")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail["code"], "chat_not_found")
        self.assertEqual(ctx.exception.detail["chatId"], "chat-missing")
        self.assertIn("会话不存在", ctx.exception.detail["message"])


if __name__ == "__main__":
    unittest.main()
