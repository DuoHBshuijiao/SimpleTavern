import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import (  # noqa: E402
    CharacterCard,
    Chat,
    ChatMessage,
    ChatOverrides,
    Settings,
    SettingsLLM,
    StateVariables,
    StatusTableDef,
    StatusTableRow,
)
from app.services import mvu_daemon  # noqa: E402
from app.services.mvu_agent import MvuAgentJob, MvuAgentRunContext, MvuAgentService  # noqa: E402
from app.routes import generate as generate_route  # noqa: E402


class MvuDaemonDirectiveRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        if hasattr(mvu_daemon, "_context_window_counts"):
            mvu_daemon._context_window_counts.clear()

    def test_effective_mode_and_directive_fall_back_to_character(self) -> None:
        character = CharacterCard(
            id="char_directive",
            name="指令角色",
            mvuMode="directive",
            mvuDirective="根据最近对话维护状态",
        )
        chat = Chat(characterId=character.id)

        mode, directive = mvu_daemon._resolve_mvu_runtime_config(chat, character)

        self.assertEqual(mode, "directive")
        self.assertEqual(directive, "根据最近对话维护状态")

        chat.overrides.mvuMode = "regex"
        chat.overrides.mvuDirective = None
        mode, directive = mvu_daemon._resolve_mvu_runtime_config(chat, character)

        self.assertEqual(mode, "regex")
        self.assertEqual(directive, "根据最近对话维护状态")

    def test_context_window_counter_starts_at_10_grows_by_2_and_wraps_after_30(self) -> None:
        got = [mvu_daemon._next_context_window_count("chat_counter") for _ in range(12)]

        self.assertEqual(got, [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 10])

    async def test_run_once_directive_runs_without_consuming_empty_regex_queue(self) -> None:
        character = CharacterCard(
            id="char_directive",
            name="指令角色",
            mvuMode="directive",
            mvuDirective="维护角色状态",
            mvuEnabled=True,
        )
        chat = Chat(
            id="chat_directive",
            characterId=character.id,
            overrides=ChatOverrides(mvuMode=None, mvuDirective=None),
            messages=[
                ChatMessage(role="assistant", content="开场"),
                ChatMessage(role="user", content="你好"),
            ],
        )

        captured_jobs = []

        class FakeAgent:
            def __init__(self, _run_ctx, **kwargs):
                pass

            async def run_job(self, job, *, on_event=None):
                captured_jobs.append(job)
                return [], []

        with (
            patch.object(mvu_daemon, "load_chat", return_value=chat),
            patch.object(mvu_daemon, "load_character", return_value=character),
            patch.object(
                mvu_daemon,
                "load_settings",
                return_value=Settings(
                    llm=SettingsLLM(
                        baseUrl="http://example.test",
                        apiKey="test-key",
                        defaultModel="mvu-model",
                    ),
                ),
            ),
            patch.object(mvu_daemon, "dequeue_by_message_id", side_effect=AssertionError("directive mode must not dequeue regex queue")),
            patch.object(mvu_daemon, "save_chat", side_effect=AssertionError("directive mode must not mark mvuProcessed")),
            patch.object(mvu_daemon, "MvuAgentService", FakeAgent),
        ):
            await mvu_daemon._run_once(chat.id)

        self.assertEqual(len(captured_jobs), 1)
        self.assertEqual(captured_jobs[0].mode, "directive")
        self.assertEqual(captured_jobs[0].directive, "维护角色状态")
        self.assertEqual(captured_jobs[0].queue_items, [])
        self.assertEqual(captured_jobs[0].context_window_count, 10)


class MvuAgentDirectivePromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_directive_job_prompt_mentions_no_regex_queue_and_done_payload(self) -> None:
        captured_messages = []

        async def fake_chat_completions_message(**kwargs):
            captured_messages.extend(kwargs["messages"])
            return SimpleNamespace(
                role="assistant",
                content="完成",
                reasoning_content=None,
                tool_calls=[],
            )

        job = MvuAgentJob(
            chat_id="chat_directive",
            character_id="char_directive",
            system_prompt="系统提示",
            state=None,
            state_markdown="（暂无状态变量）",
            queue_items=[],
            queue_text="（队列为空）",
            context_markdown="[用户]: 你好",
            mode="directive",
            directive="当关系变化时更新状态栏",
            context_window_count=12,
        )

        service = MvuAgentService(MvuAgentRunContext(base_url="http://example.test", api_key="", model="m"))
        with patch("app.services.mvu_agent.chat_completions_message", new=fake_chat_completions_message):
            events, _logs = await service.run_job(job)

        user_message = captured_messages[1]["content"]
        self.assertIn("无正则队列", user_message)
        self.assertIn("依据数据变更指令和最近对话维护状态", user_message)
        self.assertIn("当关系变化时更新状态栏", user_message)
        self.assertIn("最近 12 条", user_message)
        self.assertEqual(events[-1].kind, "done")
        self.assertEqual(events[-1].data["mode"], "directive")
        self.assertEqual(events[-1].data["queueConsumed"], 0)


class GenerateMvuStateInjectionTests(unittest.TestCase):
    def test_directive_state_tables_inject_into_last_assistant_without_mutating_chat(self) -> None:
        chat = Chat(
            characterId="char_directive",
            overrides=ChatOverrides(mvuMode="directive"),
            messages=[
                ChatMessage(role="assistant", content="旧回复"),
                ChatMessage(role="user", content="继续"),
            ],
            stateVariables=StateVariables(
                tables=[
                    StatusTableDef(
                        name="角色状态",
                        columns=["情绪"],
                        rows=[StatusTableRow(field="女主", cells={"情绪": "警惕"})],
                    )
                ]
            ),
        )
        character = CharacterCard(id="char_directive", name="指令角色")
        messages = [
            {"role": "assistant", "content": chat.messages[0].content},
            {"role": "user", "content": chat.messages[1].content},
        ]

        injected = generate_route._inject_mvu_state_tables_for_directive(messages, chat, character)

        self.assertTrue(injected)
        self.assertIn("旧回复", messages[0]["content"])
        self.assertIn("## 角色状态", messages[0]["content"])
        self.assertIn("| 女主 | 警惕 |", messages[0]["content"])
        self.assertEqual(chat.messages[0].content, "旧回复")

    def test_directive_state_tables_skip_when_no_assistant_message(self) -> None:
        chat = Chat(
            characterId="char_directive",
            overrides=ChatOverrides(mvuMode="directive"),
            messages=[ChatMessage(role="user", content="继续")],
            stateVariables=StateVariables(
                tables=[
                    StatusTableDef(
                        name="角色状态",
                        columns=["情绪"],
                        rows=[StatusTableRow(field="女主", cells={"情绪": "警惕"})],
                    )
                ]
            ),
        )
        character = CharacterCard(id="char_directive", name="指令角色")
        messages = [{"role": "user", "content": "继续"}]

        injected = generate_route._inject_mvu_state_tables_for_directive(messages, chat, character)

        self.assertFalse(injected)
        self.assertEqual(messages, [{"role": "user", "content": "继续"}])


if __name__ == "__main__":
    unittest.main()
