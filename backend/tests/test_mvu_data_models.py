"""MVU L1 数据模型校验：StatusTableDef, StatusTableRow, StateVariables, MvuWorkLogEntry, Chat.stateVariables。"""
import unittest

from app.schemas import (
    StatusTableDef,
    StatusTableRow,
    StateVariables,
    MvuWorkLogEntry,
    Chat,
)


class TestStatusTableDef(unittest.TestCase):
    def test_defaults(self) -> None:
        t = StatusTableDef(name="stats")
        self.assertEqual(t.name, "stats")
        self.assertEqual(t.columns, [])
        self.assertEqual(t.rows, [])

    def test_with_columns_and_rows(self) -> None:
        row = StatusTableRow(field="好感度", cells={"当前值": "70"})
        t = StatusTableDef(
            name="stats",
            columns=["当前值", "变化"],
            rows=[row],
        )
        self.assertEqual(t.columns, ["当前值", "变化"])
        self.assertEqual(len(t.rows), 1)
        self.assertEqual(t.rows[0].field, "好感度")

    def test_extra_fields_allow(self) -> None:
        t = StatusTableDef.model_validate({"name": "x", "extra": 1})
        self.assertEqual(t.name, "x")
        self.assertEqual(t.model_extra, {"extra": 1})


class TestStatusTableRow(unittest.TestCase):
    def test_defaults(self) -> None:
        r = StatusTableRow(field="好感度")
        self.assertEqual(r.field, "好感度")
        self.assertEqual(r.cells, {})

    def test_with_cells(self) -> None:
        r = StatusTableRow(field="好感度", cells={"当前值": "70", "变化": "+2"})
        self.assertEqual(r.cells["当前值"], "70")
        self.assertEqual(r.cells["变化"], "+2")


class TestStateVariables(unittest.TestCase):
    def test_defaults(self) -> None:
        sv = StateVariables()
        self.assertEqual(sv.version, 1)
        self.assertEqual(sv.updatedAt, "")
        self.assertEqual(sv.source, "mvu_agent")
        self.assertEqual(sv.tables, [])

    def test_with_tables(self) -> None:
        t = StatusTableDef(name="stats")
        sv = StateVariables(tables=[t], version=3, source="chat_assistant")
        self.assertEqual(sv.version, 3)
        self.assertEqual(sv.source, "chat_assistant")
        self.assertEqual(len(sv.tables), 1)
        self.assertEqual(sv.tables[0].name, "stats")

    def test_source_only_accepts_valid_literals(self) -> None:
        sv = StateVariables(source="mvu_agent")
        self.assertEqual(sv.source, "mvu_agent")
        sv2 = StateVariables(source="chat_assistant")
        self.assertEqual(sv2.source, "chat_assistant")

    def test_source_rejects_invalid_value(self) -> None:
        with self.assertRaises(Exception):
            StateVariables.model_validate({"source": "invalid"})


class TestMvuWorkLogEntry(unittest.TestCase):
    def test_defaults(self) -> None:
        e = MvuWorkLogEntry()
        self.assertTrue(len(e.id) > 0)
        self.assertEqual(e.chatId, "")
        self.assertNotEqual(e.timestamp, "")
        self.assertEqual(e.eventType, "triggered")
        self.assertEqual(e.summary, "")
        self.assertIsNone(e.detail)

    def test_with_detail(self) -> None:
        e = MvuWorkLogEntry(
            chatId="abc",
            eventType="tool_call",
            summary="更新了好感度 68→72",
            detail={"tool_name": "mvu_set_cell", "ok": True},
        )
        self.assertEqual(e.chatId, "abc")
        self.assertEqual(e.eventType, "tool_call")
        self.assertEqual(e.summary, "更新了好感度 68→72")
        self.assertEqual(e.detail["tool_name"], "mvu_set_cell")

    def test_event_type_only_accepts_valid_literals(self) -> None:
        for vt in ("triggered", "planning", "tool_call", "commit", "error"):
            e = MvuWorkLogEntry(eventType=vt)
            self.assertEqual(e.eventType, vt)

    def test_event_type_rejects_invalid_value(self) -> None:
        with self.assertRaises(Exception):
            MvuWorkLogEntry.model_validate({"eventType": "unknown"})


class TestChatStateVariables(unittest.TestCase):
    def test_defaults_to_none(self) -> None:
        c = Chat(characterId="cid")
        self.assertIsNone(c.stateVariables)

    def test_can_set_state_variables(self) -> None:
        sv = StateVariables(version=1, source="mvu_agent")
        c = Chat(characterId="cid", stateVariables=sv)
        self.assertIsNotNone(c.stateVariables)
        self.assertEqual(c.stateVariables.version, 1)

    def test_extra_allow_on_chat(self) -> None:
        c = Chat.model_validate({"characterId": "x", "extraKey": 42})
        self.assertEqual(c.model_extra, {"extraKey": 42})


if __name__ == "__main__":
    unittest.main()
