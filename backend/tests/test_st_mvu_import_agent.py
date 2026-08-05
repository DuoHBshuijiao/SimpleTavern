from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.openai_compat import ChatCompletionMessage  # noqa: E402
from app.services.st_mvu_import_agent import StMvuImportAgentRunContext, run_st_mvu_import_agent  # noqa: E402


class StMvuImportAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_receives_full_st_context_and_materializes_tool_writes(self) -> None:
        raw = {
            "spec": "chara_card_v3",
            "data": {
                "name": "完整上下文角色",
                "description": "desc",
                "extensions": {
                    "tavern_helper": {"script": "function updateMood(){ return state.mood }"},
                    "regex_scripts": [
                        {
                            "scriptName": "复杂 UI",
                            "findRegex": r"<div class=\"panel\">([\s\S]*?)</div>",
                            "replaceString": "<button onclick=\"doThing()\">更新复杂状态</button>",
                        }
                    ],
                },
                "character_book": {
                    "entries": [
                        {
                            "comment": "状态字段定义",
                            "content": "生命值、位置、心情都需要在状态栏维护。",
                            "keys": ["状态栏"],
                            "enabled": True,
                        }
                    ],
                },
            },
        }
        calls = []

        async def fake_chat_completions_message(**kwargs):
            calls.append(kwargs)
            return ChatCompletionMessage(
                role="assistant",
                content="",
                reasoning_content=None,
                tool_calls=[
                    {
                        "id": "call_directive",
                        "type": "function",
                        "function": {
                            "name": "st_mvu_set_directive",
                            "arguments": json.dumps({
                                "directive": "根据对话维护生命值、位置与心情。",
                                "summary": "从完整 ST 脚本和世界书提取状态需求。",
                                "warnings": ["复杂 UI 脚本已作为语义线索处理。"],
                                "confidence": 0.9,
                            }, ensure_ascii=False),
                        },
                    },
                    {
                        "id": "call_table",
                        "type": "function",
                        "function": {
                            "name": "st_mvu_define_initial_table",
                            "arguments": json.dumps({
                                "name": "角色状态",
                                "columns": ["当前值"],
                                "rows": [{"field": "生命值", "cells": {"当前值": "待观察"}}],
                            }, ensure_ascii=False),
                        },
                    },
                    {
                        "id": "call_finish",
                        "type": "function",
                        "function": {
                            "name": "st_mvu_finish",
                            "arguments": json.dumps({"summary": "MVU Agent 已完成导入分析。"}, ensure_ascii=False),
                        },
                    },
                ],
            )

        with patch("app.services.st_mvu_import_agent.chat_completions_message", side_effect=fake_chat_completions_message):
            result = await run_st_mvu_import_agent(
                raw,
                run_ctx=StMvuImportAgentRunContext(
                    base_url="http://example.test/v1",
                    api_key="test",
                    model="fake-model",
                    max_tool_turns=1,
                    protocol="openai_compatible_chat",
                ),
            )

        self.assertEqual(result["directive"], "根据对话维护生命值、位置与心情。")
        self.assertEqual(result["initialStateTables"][0]["name"], "角色状态")
        self.assertIn("复杂 UI 脚本", result["warnings"][0])
        prompt_context = calls[0]["messages"][1]["content"]
        self.assertEqual(calls[0]["protocol"], "openai_compatible_chat")
        self.assertIn("<button onclick=", prompt_context)
        self.assertIn("生命值、位置、心情都需要在状态栏维护", prompt_context)


if __name__ == "__main__":
    unittest.main()
