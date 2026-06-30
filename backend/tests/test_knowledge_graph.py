"""知识图谱领域服务单元测试。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.schemas import KgEntity, KgRelation, KnowledgeGraph
from app.services.knowledge_graph import (
    has_graph_data,
    render_context_text,
    upsert_entity,
    upsert_relation,
    delete_entity,
    KnowledgeGraphError,
)


class TestRenderContextText(unittest.TestCase):
    def test_includes_type_sections(self):
        kg = KnowledgeGraph(
            entities=[
                KgEntity(id="e1", name="张三", type="人物", properties={"年龄": "32"}),
                KgEntity(id="e2", name="德月楼", type="地点", properties={}),
            ],
            relations=[],
        )
        text = render_context_text(kg)
        self.assertIn("[人物]", text)
        self.assertIn("[地点]", text)
        self.assertIn("张三", text)
        self.assertIn("德月楼", text)

    def test_empty_entities_returns_empty(self):
        kg = KnowledgeGraph(entities=[], relations=[])
        self.assertEqual(render_context_text(kg), "")


class TestHasGraphData(unittest.TestCase):
    def test_deleted_entities_not_counted(self):
        kg = KnowledgeGraph(
            entities=[KgEntity(id="e1", name="x", type="人物", deleted=True)],
            relations=[],
        )
        self.assertFalse(has_graph_data(kg))


class TestUpsertEntityDedup(unittest.TestCase):
    @patch("app.services.knowledge_graph.save_knowledge_graph")
    @patch("app.services.knowledge_graph.load_knowledge_graph")
    @patch("app.services.knowledge_graph._require_mvu_enabled")
    def test_merge_by_name_and_type(self, _mvu, load_mock, save_mock):
        load_mock.return_value = KnowledgeGraph(
            entities=[KgEntity(id="existing", name="张三", type="人物", properties={"年龄": "30"})],
            relations=[],
            version=1,
        )
        save_mock.side_effect = lambda _cid, kg: kg

        kg, eid = upsert_entity(
            "chat1",
            name="张三",
            entity_type="人物",
            properties={"职业": "侦探"},
            source="mvu_agent",
        )
        self.assertEqual(eid, "existing")
        ent = next(e for e in kg.entities if e.id == "existing")
        self.assertEqual(ent.properties.get("年龄"), "30")
        self.assertEqual(ent.properties.get("职业"), "侦探")
        self.assertEqual(kg.version, 2)


class TestRelationValidation(unittest.TestCase):
    @patch("app.services.knowledge_graph.save_knowledge_graph")
    @patch("app.services.knowledge_graph.load_knowledge_graph")
    @patch("app.services.knowledge_graph._require_mvu_enabled")
    def test_missing_subject_raises(self, _mvu, load_mock, save_mock):
        load_mock.return_value = KnowledgeGraph(
            entities=[KgEntity(id="e1", name="A", type="人物")],
            relations=[],
        )
        with self.assertRaises(KnowledgeGraphError):
            upsert_relation(
                "chat1",
                subject_id="missing",
                predicate="认识",
                object_id="e1",
            )


class TestDeleteEntity(unittest.TestCase):
    @patch("app.services.knowledge_graph.save_knowledge_graph")
    @patch("app.services.knowledge_graph.load_knowledge_graph")
    @patch("app.services.knowledge_graph._require_mvu_enabled")
    def test_cascades_relations(self, _mvu, load_mock, save_mock):
        load_mock.return_value = KnowledgeGraph(
            entities=[
                KgEntity(id="e1", name="A", type="人物"),
                KgEntity(id="e2", name="B", type="人物"),
            ],
            relations=[
                KgRelation(subject="e1", predicate="认识", object="e2"),
            ],
            version=1,
        )
        save_mock.side_effect = lambda _cid, kg: kg
        kg = delete_entity("chat1", "e1")
        self.assertTrue(any(e.id == "e1" and e.deleted for e in kg.entities))
        self.assertEqual(len(kg.relations), 0)


if __name__ == "__main__":
    unittest.main()
