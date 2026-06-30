"""Tests for knowledge graph RP injection."""

from __future__ import annotations

from types import SimpleNamespace

from app.kg_inject import (
    apply_knowledge_graph_injection,
    format_knowledge_graph_block,
    is_knowledge_graph_enabled,
)
from app.mvu_system_prompt import load_mvu_system_prompt


def _chat(*, kg_enabled=None, position=None, depth=5, role="assistant"):
    return SimpleNamespace(
        overrides=SimpleNamespace(
            knowledgeGraphEnabled=kg_enabled,
            knowledgeGraphInjectPosition=position,
            knowledgeGraphInjectDepth=depth,
            knowledgeGraphBeforeLastRole=role,
        ),
    )


def test_is_knowledge_graph_enabled_defaults():
    assert is_knowledge_graph_enabled(_chat()) is True
    assert is_knowledge_graph_enabled(_chat(kg_enabled=None)) is True
    assert is_knowledge_graph_enabled(_chat(kg_enabled=False)) is False


def test_legacy_appends_to_last_assistant():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    chat = _chat(position=None)
    body = "实体A"
    assert apply_knowledge_graph_injection(messages, chat, body) is True
    assert "<KnowledgeGraph>" in messages[2]["content"]
    assert "实体A" in messages[2]["content"]
    assert messages[0]["content"] == "sys"


def test_after_system_appends_to_first_system():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    chat = _chat(position="after_system")
    assert apply_knowledge_graph_injection(messages, chat, "x") is True
    assert "<KnowledgeGraph>" in messages[0]["content"]
    assert messages[1]["content"] == "hi"


def test_before_last_inserts_system_before_role():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    chat = _chat(position="before_last", role="assistant")
    assert apply_knowledge_graph_injection(messages, chat, "kg") is True
    assert messages[2]["role"] == "system"
    assert "<KnowledgeGraph>" in messages[2]["content"]
    assert messages[3]["role"] == "assistant"


def test_depth_inserts_at_conversation_index():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    chat = _chat(position="depth", depth=1)
    assert apply_knowledge_graph_injection(messages, chat, "kg") is True
    # depth 1 from tail (u2,a1,u1) -> before u2 at index 3
    assert messages[3]["role"] == "system"
    assert "<KnowledgeGraph>" in messages[3]["content"]


def test_load_mvu_prompt_strips_kg_when_disabled():
    full = load_mvu_system_prompt(include_knowledge_graph=True)
    slim = load_mvu_system_prompt(include_knowledge_graph=False)
    assert "kg_upsert_entity" in full
    assert "kg_upsert_entity" not in slim
    assert "知识图谱原则" not in slim
    assert "6. 如需要，调用 `read_mvu_logs`" in slim
