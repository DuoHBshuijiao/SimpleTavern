import asyncio
import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.fork_index import _fork_index_path
from app.llm.providers.openai_compatible_chat import ChatCompletionMessage, StreamChunk
from app.routes import assistant, chats, import_export, settings as settings_routes
from app.schemas import CharacterCard, Chat, ChatMessage, Settings, WorldBook
from app.storage import ensure_data_initialized, load_chat, load_worldbook, save_character, save_chat, save_settings, save_worldbook
from app.worldbook_index import list_active_worldbook_ids


class ChecklistRoutesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": directory.name}))
        ensure_data_initialized()
        app = FastAPI()
        for route in (assistant, chats, import_export, settings_routes):
            app.include_router(route.router)
        self.client = await self.enterAsyncContext(AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost"))
        self.card = save_character(CharacterCard(name="Local fixture"))

    async def test_janitor_pending_is_consumed_once_and_requires_existing_character(self):
        source = {"chatMessages": [
            {"is_main": True, "is_bot": False, "message": "question", "created_at": "2025-01-01"},
            {"is_main": True, "is_bot": True, "message": "main answer", "created_at": "2025-01-02"},
            {"is_main": False, "is_bot": True, "message": "alternative", "created_at": "2025-01-03"},
        ]}
        pending = (await self.client.post("/import/janitor/pending", json=source)).json()["pendingId"]
        preview = await self.client.get(f"/import/janitor/pending/{pending}")
        self.assertEqual(preview.json()["preview"]["messageCount"], 2)
        missing = await self.client.post("/import/janitor/confirm", json={"pendingId": pending, "characterId": "gone"})
        self.assertEqual(missing.status_code, 404)
        body = {"pendingId": pending, "characterId": self.card.id}
        responses = await asyncio.gather(*(self.client.post("/import/janitor/confirm", json=body) for _ in range(2)))
        self.assertEqual(sorted(result.status_code for result in responses), [200, 404])
        result = next(result for result in responses if result.is_success)
        chat = load_chat(result.json()["chat"]["id"])
        self.assertEqual([message.content for message in chat.messages], ["question", "main answer"])
        self.assertEqual((await self.client.get(f"/import/janitor/pending/{pending}")).status_code, 404)

    async def test_janitor_rejects_empty_greetings_and_reads_later_embedded_data(self):
        for messages in ([None], [" "], [None, " 	"]):
            result = await self.client.post("/import/janitor/character-json", json={"charJson": {"first_messages": messages}})
            self.assertEqual(result.status_code, 400, result.text)
        blocks = [
            {"firstStore": {"state": "unrelated"}},
            {"compiledcharacterStore": {"character": {
                "name": "Complete fixture", "description": "Known definition", "first_messages": [None, "Hello", "Second"],
            }}},
        ]
        html = "".join(f"<script>window.mbxM.push(JSON.parse({json.dumps(json.dumps(block))}))</script>" for block in blocks)
        card, _ = import_export._parse_character_from_html(html)
        self.assertEqual((card.name, card.description, card.firstMessage), ("Complete fixture", "Known definition", "Hello"))
        self.assertEqual([entry.text for entry in card.extraFirstMessageEntries], ["Second"])

    async def test_regex_preview_shares_extraction_and_invalid_rule_does_not_block_other_settings(self):
        rules = [
            {"id": "bad", "name": "Malformed fixture", "pattern": "("},
            {"id": "valid", "pattern": r"state=(\w+)", "action": "extract_and_replace", "replacement": "display",
             "extractSource": "capture_group", "extractGroupIndex": 1},
        ]
        result = await self.client.post("/settings/content-regex/preview", json={"text": "state=ready", "rules": rules})
        self.assertEqual(result.status_code, 200, result.text)
        preview = result.json()
        self.assertEqual(preview["afterText"], "state=ready")
        self.assertEqual(preview["displayText"], "display")
        self.assertEqual(preview["errors"][0]["ruleId"], "bad")
        self.assertEqual([entry["value"] for entry in preview["extractedItems"]], ["ready"])
        settings = Settings(contentRegexRuleLibrary=rules)
        result = await self.client.put("/settings", json=settings.model_dump(mode="json"))
        self.assertEqual(result.status_code, 200, result.text)

    async def test_fork_retains_session_books_and_index_repairs_without_stale_warning(self):
        anchor = ChatMessage(role="user",content="Anchor")
        source = save_chat(Chat(characterId=self.card.id, messages=[anchor]))
        book = save_worldbook(WorldBook(name="Session book", sessionChatIds=[source.id]))
        result = await self.client.post(f"/chats/{source.id}/fork", json={"forkAtMessageId": anchor.id})
        self.assertEqual(result.status_code, 200, result.text)
        fork = result.json()
        self.assertEqual(load_worldbook(book.id).sessionChatIds, [source.id, fork["id"]])
        self.assertIn(book.id, list_active_worldbook_ids(fork["id"]))
        _fork_index_path().write_text("{broken", encoding="utf-8")
        for _ in range(2):
            lineage = (await self.client.get(f"/chats/{source.id}/fork-lineage")).json()
            self.assertEqual(lineage["outgoingForks"][0]["count"], 1)
            self.assertEqual(lineage["outgoingForks"][0]["chats"][0]["createdAt"], fork["createdAt"])
            self.assertFalse(lineage["warnings"])

    async def test_chat_regex_order_persists_without_promoting_role_rules(self):
        save_settings(Settings(contentRegexRuleLibrary=[{"id": "global", "pattern": "original", "order": 0}]))
        chat = save_chat(Chat(characterId=self.card.id, overrides={
            "contentRegexRules": [{"id": "role", "pattern": "role rule", "order": 1}],
        }))
        response = await self.client.put(f"/chats/{chat.id}", json={"overrides": {
            "contentRegexEnabledByRuleId": {"global": False},
            "contentRegexOrderByRuleId": {"role": 0, "global": 1},
        }})
        self.assertEqual(response.status_code, 200, response.text)
        overrides = load_chat(chat.id).overrides
        self.assertEqual(overrides.contentRegexOrderByRuleId, {"role": 0, "global": 1})
        self.assertEqual(overrides.contentRegexEnabledByRuleId, {"global": False})
        self.assertEqual([rule.id for rule in overrides.contentRegexRules], ["role"])
        self.assertEqual([rule["id"] for rule in (await self.client.get("/settings")).json()["contentRegexRuleLibrary"]], ["global"])

    async def test_search_projects_unicode_casefold_to_original_codepoint_range(self):
        chat = save_chat(Chat(characterId=self.card.id, messages=[ChatMessage(
            role="assistant", content=("İ" * 80) + " 🎲 Straße finishing",
        )]))
        response = await self.client.get(f"/chats/{chat.id}/search", params={"q": "STRASSE"})
        hit = response.json()["hits"][0]
        self.assertEqual(hit["snippet"][hit["matchStart"]:hit["matchEnd"]], "Straße")

    async def test_character_export_discloses_missing_attachment_before_download(self):
        existing = save_worldbook(WorldBook(name="Present"))
        card = save_character(CharacterCard(name="Bundle", attachedWorldBookIds=[existing.id, "gone"]))
        response = await self.client.get(f"/characters/{card.id}/export", params={"include_world_books": True})
        self.assertEqual(response.headers["x-st-export-missing"], "1")
        with zipfile.ZipFile(io.BytesIO(response.content)) as package:
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual(manifest["warnings"][0]["worldBookId"], "gone")
            self.assertEqual(manifest["exportedWorldBookIds"], [existing.id])
            exported_card = json.loads(package.read(f"characters/{card.id}.json"))
            self.assertEqual(exported_card["attachedWorldBookIds"], [existing.id])

    def setup_assistant_model(self, stream_enabled):
        settings = Settings(streamEnabled=stream_enabled)
        settings.llm.baseUrl = "http://localhost:1"
        settings.llm.apiKey = "mock-key"
        settings.llm.defaultModel = "fixture"
        save_settings(settings)

    async def test_assistant_rewrites_from_anchor_and_keeps_failed_branch(self):
        from app.services import assistant_agent

        for stream_enabled in (False, True):
            self.setup_assistant_model(stream_enabled)
            chat = save_chat(Chat(characterId=self.card.id))
            path = f"/assistant/chat/messages?chatId={chat.id}"
            for role, text in (("user", "first"), ("assistant", "old answer"), ("user", "later")):
                response = await self.client.post(path, json={"role": role, "content": text})
            original = response.json()["messages"]
            target = original[1]["id"]

            async def complete(**options):
                texts = [m["content"] for m in options["messages"]]
                self.assertIn("first", texts)
                self.assertNotIn("later", texts)
                return ChatCompletionMessage(role="assistant", content="replacement", reasoning_content=None, tool_calls=None)
            async def stream(**options):
                yield StreamChunk(kind="content", text=(await complete(**options)).content)
                yield StreamChunk(kind="finish")
            body = {"userMessage": "", "appendUserMessage": False, "chatId": chat.id, "regenerateFromMessageId": target}
            async def blank(**_options):
                return ChatCompletionMessage(role="assistant", content=" ", reasoning_content=None, tool_calls=None)
            async def blank_stream(**_options):
                yield StreamChunk(kind="content", text=" ")
                yield StreamChunk(kind="finish")
            with patch.object(assistant_agent, "chat_completions_message", blank), patch.object(
                assistant_agent, "stream_chat_completions", blank_stream,
            ):
                failed = await self.client.post("/assistant/stream", json=body)
            self.assertIn("assistant_empty_rewrite", failed.text)
            self.assertEqual((await self.client.get(f"/assistant/chat?chatId={chat.id}")).json()["messages"], original)

            with patch.object(assistant_agent, "chat_completions_message", complete), patch.object(
                assistant_agent, "stream_chat_completions", stream,
            ):
                generated = await self.client.post("/assistant/stream", json=body)
            self.assertEqual(generated.status_code, 200, generated.text)
            current = (await self.client.get(f"/assistant/chat?chatId={chat.id}")).json()["messages"]
            self.assertEqual([item["content"] for item in current], ["first", "replacement"])
            self.assertEqual(current[1]["id"], target)

    async def test_workspace_reset_prevents_pending_assistant_from_writing(self):
        from app.services import assistant_agent

        self.setup_assistant_model(False)
        started, release = asyncio.Event(), asyncio.Event()

        async def complete(**_kwargs):
            started.set()
            await release.wait()
            return ChatCompletionMessage(role="assistant", content="late fixture", reasoning_content=None, tool_calls=None)

        with patch.object(assistant_agent, "chat_completions_message", complete):
            pending = asyncio.create_task(self.client.post("/assistant/stream", json={
                "scope": "workspace", "userMessage": "old fixture",
            }))
            await asyncio.wait_for(started.wait(), 2)
            reset = await self.client.post("/assistant/workspace/chat/delete")
            self.assertEqual(reset.status_code, 200)
            release.set()
            self.assertEqual((await pending).status_code, 409)
        current = (await self.client.get("/assistant/chat?scope=workspace")).json()
        self.assertEqual(current["messages"], [])

    def test_orphaned_tool_result_is_excluded(self):
        call = {"id":"called", "type":"function", "function":{"name":"fixture", "arguments":"{}"}}
        histories = [
            ChatMessage(role="assistant", content="", tool_calls=[call]),
            ChatMessage(role="tool", content="valid", tool_call_id="called"),
            ChatMessage(role="tool", content="orphaned", tool_call_id="removed"),
        ]
        result = assistant._assistant_messages_to_openai(histories)
        self.assertEqual([item["content"] for item in result], ["", "valid"])
