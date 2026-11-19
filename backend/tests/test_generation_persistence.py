import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.routes import chats, generate, settings as settings_routes
from app.schemas import CharacterCard, Chat, ChatMessage, Settings, StateVariables
from app.storage import chat_dir, delete_character, load_chat, load_settings, save_character, save_chat, save_settings


class GenerationPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        environment = patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": folder.name})
        environment.start()
        self.addCleanup(environment.stop)
        app = FastAPI()
        app.include_router(chats.router)
        app.include_router(generate.router)
        app.include_router(settings_routes.router)
        self.client = await self.enterAsyncContext(AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost"))
        self.character = save_character(CharacterCard(name="Character"))

    async def test_generation_saves_into_the_current_chat_and_settings(self):
        for endpoint in ("stream", "group", "interject"):
            for streaming in (True, False):
                with self.subTest(endpoint=endpoint, streaming=streaming):
                    await self.check_generation(endpoint, streaming)

    async def test_saving_an_old_settings_draft_keeps_new_server_model_history(self):
        config = Settings()
        config.llm.defaultModel = "newly-used"
        config.llm.modelCandidates = ["removed", "newly-used"]
        config.llm.usedModels = ["removed"]
        draft = save_settings(config).model_copy(deep=True)
        newest = load_settings()
        newest.llm.usedModels.insert(0, "newly-used")
        save_settings(newest)
        draft.llm.modelCandidates.remove("removed")
        draft.llm.usedModels = []
        draft.prompts.globalSystem = "edited prompt"
        response = await self.client.put("/settings", json=draft.model_dump(mode="json"))
        self.assertEqual(response.status_code, 200, response.text)
        current = load_settings()
        self.assertEqual(current.llm.usedModels, ["newly-used"])
        self.assertEqual(current.prompts.globalSystem, "edited prompt")

    async def test_nonstream_disconnect_cancels_upstream_without_assistant_write(self):
        from app.schemas import GenerateStreamRequest

        settings = Settings(streamEnabled=False)
        settings.llm.baseUrl = "http://localhost:1"
        settings.llm.apiKey = "test-key"
        settings.llm.defaultModel = "fixture"
        save_settings(settings)
        chat = save_chat(Chat(characterId=self.character.id))
        started = asyncio.Event()
        disconnected = asyncio.Event()
        upstream_cancelled = asyncio.Event()

        async def complete(**_options):
            started.set()
            try:
                await asyncio.Future()
            finally:
                upstream_cancelled.set()

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        with patch.object(generate, "chat_completions_message", complete):
            req = GenerateStreamRequest(chatId=chat.id, userMessage="pending", appendUserMessage=True)
            response_task = asyncio.create_task(generate.generate_stream(req, Request({"type": "http"}, receive=receive)))
            await asyncio.wait_for(started.wait(), 2)
            disconnected.set()
            response = await response_task
        self.assertEqual(response.status_code, 499)
        self.assertTrue(upstream_cancelled.is_set())
        self.assertEqual([message.role for message in load_chat(chat.id).messages], ["user"])

    async def check_generation(self, endpoint, streaming):
        settings = Settings(streamEnabled=streaming)
        settings.llm.baseUrl = "http://localhost:1"
        settings.llm.apiKey = "test-key"
        settings.llm.defaultModel = "test-model"
        save_settings(settings)
        group = endpoint != "stream"
        character_id = self.character.id
        old_message = ChatMessage(role="user", content="original")
        chat = save_chat(Chat(
            characterId=character_id,
            title="before",
            isGroup=group,
            memberIds=[character_id] if group else [],
            messages=[old_message],
        ))

        async def edit_while_generating():
            update = await self.client.put(f"/chats/{chat.id}", json={
                "title": "after", "overrides": {"longTermMemory": "new memory"},
            })
            self.assertEqual(update.status_code, 200, update.text)
            update = await self.client.put(f"/chats/{chat.id}/messages/{old_message.id}", json={
                "role": "user", "content": "edited",
            })
            self.assertEqual(update.status_code, 200, update.text)
            settings.prompts.globalSystem = "new prompt"
            settings.llm.usedModels = ["another-model"]
            update = await self.client.put("/settings", json=settings.model_dump(mode="json"))
            self.assertEqual(update.status_code, 200, update.text)

        async def fake_stream(**_kwargs):
            yield SimpleNamespace(kind="content", text="new ")
            await edit_while_generating()
            yield SimpleNamespace(kind="content", text="reply")

        async def fake_response(**_kwargs):
            await edit_while_generating()
            return SimpleNamespace(content="new reply", reasoning_content="provider reasoning", usage=None)

        body = {"chatId": chat.id, "characterId": character_id} if group else {
            "chatId": chat.id, "userMessage": "next question", "appendUserMessage": True,
        }
        with patch.object(generate, "stream_chat_completions", fake_stream), patch.object(
            generate, "chat_completions_message", fake_response,
        ):
            response = await self.client.post(f"/generate/{endpoint}", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('"assistantMessageId"', response.text)
        stored = load_chat(chat.id)
        self.assertEqual(stored.title, "after")
        self.assertEqual(stored.overrides.longTermMemory, "new memory")
        self.assertEqual(stored.messages[0].content, "edited")
        self.assertEqual(stored.messages[-1].content, "new reply")
        self.assertTrue(stored.messages[-1].generationMetadata)
        if not streaming:
            self.assertEqual(stored.messages[-1].reasoningContent, "provider reasoning")
        if not group:
            self.assertEqual(stored.messages[1].content, "next question")
        current_settings = load_settings()
        self.assertEqual(current_settings.prompts.globalSystem, "new prompt")
        self.assertEqual(current_settings.llm.usedModels, ["another-model"] if group else ["test-model", "another-model"])

    async def test_delete_character_removes_chat_directories_including_lock_files(self):
        character_id = self.character.id
        chat = save_chat(Chat(characterId=character_id))
        load_chat(chat.id)
        character_chats = chat_dir(character_id)
        self.assertTrue(list(character_chats.rglob("*.lock")))
        delete_character(character_id)
        self.assertFalse(character_chats.exists())
        with self.assertRaises(FileNotFoundError):
            load_chat(chat.id)

    async def test_group_summary_reads_metadata_before_large_mvu_state(self):
        chat = save_chat(Chat(
            characterId=self.character.id,
            title="Large group",
            isGroup=True,
            memberIds=[self.character.id],
            messages=[ChatMessage(role="user", content="history " * 900)],
            stateVariables=StateVariables(largeStateFixture="state " * 9000),
            createdAt="2026-01-01T00:00:00+00:00",
            updatedAt="2026-02-01T00:00:00+00:00",
        ))
        response = await self.client.get("/chats/groups?summary=1")
        self.assertEqual(response.status_code, 200, response.text)
        summary, = response.json()
        self.assertEqual(summary["id"], chat.id)
        self.assertEqual(summary["memberIds"], chat.memberIds)
        self.assertEqual(summary["createdAt"], chat.createdAt)
        self.assertEqual(summary["updatedAt"], chat.updatedAt)

    async def test_edit_updates_only_the_selected_message_variant(self):
        message = ChatMessage(role="assistant", content="Second", greetingVariants=["First", "Second"], greetingVariantIndex=1)
        chat = save_chat(Chat(characterId=self.character.id, messages=[message]))
        response = await self.client.put(f"/chats/{chat.id}/messages/{message.id}", json={
            "role": "assistant", "content": "Edited second",
        })
        self.assertEqual(response.status_code, 200, response.text)
        saved, = load_chat(chat.id).messages
        self.assertEqual(saved.content, "Edited second")
        self.assertEqual(saved.greetingVariants, ["First", "Edited second"])
        self.assertEqual(saved.greetingVariantIndex, 1)

    async def test_empty_rewrite_returns_an_error_and_keeps_original_reply_and_tail(self):
        settings = Settings()
        settings.llm.baseUrl = "http://localhost:1"
        settings.llm.apiKey = "test-key"
        settings.llm.defaultModel = "test-model"
        save_settings(settings)
        original = ChatMessage(role="assistant", content="Original answer")
        followup = ChatMessage(role="user", content="Keep this followup")
        chat = save_chat(Chat(characterId=self.character.id, messages=[original, followup]))

        async def blank_stream(**_kwargs):
            yield SimpleNamespace(kind="content", text=" \n  ")

        with patch.object(generate, "stream_chat_completions", blank_stream):
            response = await self.client.post("/generate/stream", json={
                "chatId": chat.id,
                "userMessage": "Previous question",
                "appendUserMessage": False,
                "omitMessageIds": [original.id, followup.id],
                "mergeAssistantIntoMessageId": original.id,
            })
        self.assertIn("empty_generation", response.text)
        self.assertNotIn("event: done", response.text)
        self.assertEqual(load_chat(chat.id).messages, [original, followup])
