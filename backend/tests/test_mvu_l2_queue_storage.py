"""MVU L2 测试：dequeue_batch + mvu_logs 存储 + stateVariables 读写。"""
import unittest
from unittest.mock import patch, MagicMock

from app.content_regex_queue import (
    enqueue_content_regex_items,
    dequeue_batch,
    get_content_regex_queue_size,
)
from app.schemas import MvuWorkLogEntry, StateVariables, Chat


class TestDequeueBatch(unittest.TestCase):
    def setUp(self) -> None:
        self.chat_id = "test-dequeue-chat"
        while get_content_regex_queue_size(self.chat_id) > 0:
            dequeue_batch(self.chat_id, 100)

    def test_returns_list(self) -> None:
        result = dequeue_batch(self.chat_id, 5)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_dequeues_all_when_fewer_than_max(self) -> None:
        items = [
            {"ruleId": "1", "value": "a"},
            {"ruleId": "2", "value": "b"},
            {"ruleId": "3", "value": "c"},
        ]
        enqueue_content_regex_items(self.chat_id, items)
        batch = dequeue_batch(self.chat_id, 10)
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0]["value"], "a")
        self.assertEqual(batch[2]["value"], "c")
        self.assertEqual(get_content_regex_queue_size(self.chat_id), 0)

    def test_dequeues_up_to_max(self) -> None:
        items = [{"ruleId": str(i), "value": str(i)} for i in range(10)]
        enqueue_content_regex_items(self.chat_id, items)
        batch = dequeue_batch(self.chat_id, 4)
        self.assertEqual(len(batch), 4)
        self.assertEqual(get_content_regex_queue_size(self.chat_id), 6)

    def test_returns_copy_not_reference(self) -> None:
        enqueue_content_regex_items(self.chat_id, [{"ruleId": "x", "value": "v"}])
        batch = dequeue_batch(self.chat_id, 1)
        batch[0]["value"] = "mutated"
        # mutation should not affect queue internals
        self.assertEqual(get_content_regex_queue_size(self.chat_id), 0)


class TestMvuLogsStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.cid = "test-char"
        self.chat_id = "test-chat-mvu-logs"

    def test_load_returns_empty_list_when_file_missing(self) -> None:
        from app.storage import _mvu_logs_path

        path = _mvu_logs_path(self.cid, self.chat_id)
        # ensure no file exists
        if path.exists():
            path.unlink()
        from app.storage import load_mvu_logs
        entries = load_mvu_logs(self.cid, self.chat_id)
        self.assertEqual(entries, [])

    def test_save_and_load_roundtrip(self) -> None:
        from app.storage import _mvu_logs_path, load_mvu_logs, save_mvu_logs

        entries = [
            MvuWorkLogEntry(
                id="e1", chatId=self.chat_id, eventType="triggered",
                summary="MVU 触发", detail=None,
            ),
            MvuWorkLogEntry(
                id="e2", chatId=self.chat_id, eventType="tool_call",
                summary="更新了好感度", detail={"tool": "mvu_set_cell"},
            ),
        ]
        save_mvu_logs(self.cid, self.chat_id, entries)
        loaded = load_mvu_logs(self.cid, self.chat_id)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].id, "e1")
        self.assertEqual(loaded[0].eventType, "triggered")
        self.assertEqual(loaded[1].summary, "更新了好感度")

        # cleanup
        path = _mvu_logs_path(self.cid, self.chat_id)
        if path.exists():
            path.unlink()

    def test_rotation_at_200(self) -> None:
        from app.storage import _mvu_logs_path, load_mvu_logs, save_mvu_logs

        entries = [
            MvuWorkLogEntry(chatId=self.chat_id, summary=f"entry {i}")
            for i in range(250)
        ]
        save_mvu_logs(self.cid, self.chat_id, entries)
        loaded = load_mvu_logs(self.cid, self.chat_id)
        self.assertEqual(len(loaded), 200)
        # oldest 50 should be dropped; first kept should be index 50
        self.assertEqual(loaded[0].summary, "entry 50")
        self.assertEqual(loaded[-1].summary, "entry 249")

        path = _mvu_logs_path(self.cid, self.chat_id)
        if path.exists():
            path.unlink()


class TestStateVariablesStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.chat_id = "test-chat-sv"

    @patch("app.storage.save_chat")
    @patch("app.storage.load_chat")
    def test_load_returns_none_when_chat_has_no_state(self, mock_load, _mock_save) -> None:
        chat = Chat(characterId="cid", stateVariables=None)
        mock_load.return_value = chat
        from app.storage import load_chat_state_variables
        result = load_chat_state_variables(self.chat_id)
        self.assertIsNone(result)

    @patch("app.storage.save_chat")
    @patch("app.storage.load_chat")
    def test_load_returns_state_variables(self, mock_load, _mock_save) -> None:
        sv = StateVariables(version=5, source="mvu_agent")
        chat = Chat(characterId="cid", stateVariables=sv)
        mock_load.return_value = chat
        from app.storage import load_chat_state_variables
        result = load_chat_state_variables(self.chat_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.version, 5)

    @patch("app.storage.save_chat")
    @patch("app.storage.load_chat")
    def test_save_increments_version(self, mock_load, mock_save) -> None:
        chat = Chat(characterId="cid")
        mock_load.return_value = chat
        mock_save.side_effect = lambda c: c

        state = StateVariables(version=3, source="mvu_agent")
        from app.storage import save_chat_state_variables
        result = save_chat_state_variables(self.chat_id, state)

        self.assertIsNotNone(result.stateVariables)
        self.assertEqual(result.stateVariables.version, 4)
        self.assertNotEqual(result.stateVariables.updatedAt, "")


if __name__ == "__main__":
    unittest.main()
