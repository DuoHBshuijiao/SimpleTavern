import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.handlers.workspace import handle_workspace_write_file
from app.content_regex import apply_content_regex_pipeline
from app.kg_inject import resolve_inject_depth
from app.local_requests import LocalRequestMiddleware
from app.routes import assistant, clipboard, tts, update
from app.schemas import AssistantSettings, Chat, ChatContentRegexRule, ChatOverrides
from app.services.pricing import estimate_cost_from_usage
from app.services.sillytavern_worldbook import build_worldbook
from app.services.usage_ledger import summarize_ledger_events
from app.storage import assistant_chat_ingest_dir, save_chat
from app.regex_compat import compile_timed_user_regex


class DesktopAuditTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        environment = patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": temp.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_workspace_write_requires_destructive_permission_only_for_existing_file(self):
        context = AssistantToolContext(None, None, False, False, AssistantSettings())
        new_file = handle_workspace_write_file(context, {"path": "notes.txt", "content": "original"})
        self.assertTrue(new_file["ok"])
        denied = handle_workspace_write_file(context, {"path": "notes.txt", "content": ""})
        self.assertFalse(denied["ok"])
        from app.assistant_tools.paths import resolve_ai_path
        self.assertEqual(resolve_ai_path("notes.txt").read_text(encoding="utf-8"), "original")

    def test_reset_requires_chat_id_and_scopes_attachment_cleanup(self):
        paths = []
        for character in ("alice", "bob"):
            chat = save_chat(Chat(characterId=character))
            folder = assistant_chat_ingest_dir(chat.id)
            folder.mkdir(parents=True)
            path = folder / "attachment.txt"
            path.write_text(character, encoding="utf-8")
            paths.append((chat.id, path))
        with self.assertRaises(HTTPException) as error:
            assistant.reset_assistant(chatId=None, scope=None)
        self.assertEqual(error.exception.status_code, 400)
        self.assertTrue(all(path.is_file() for _, path in paths))
        assistant.reset_assistant(chatId=paths[0][0], scope=None)
        self.assertFalse(paths[0][1].exists())
        self.assertTrue(paths[1][1].is_file())

    def test_audio_cache_accepts_only_supported_formats(self):
        with self.assertRaises(ValidationError):
            tts.SynthesizeReq(text="hello", voice_id="sample", audio_format="unknown")
        with self.assertRaises(HTTPException):
            tts._store_cached_audio(b"data", "unknown")
        asset_id = tts._store_cached_audio(b"data", "wav")
        self.assertEqual((tts.get_tts_cache_dir() / f"{asset_id}.wav").read_bytes(), b"data")

    def test_invalid_update_tag_is_rejected_before_downloading(self):
        with patch.object(update.httpx, "stream") as stream:
            with self.assertRaises(HTTPException) as error:
                update.download_update({"tagName": "invalid tag"})
            self.assertEqual(error.exception.status_code, 400)
            stream.assert_not_called()

    def test_expensive_regex_times_out_and_pipeline_continues(self):
        rules = [
            ChatContentRegexRule(pattern="(a|aa)+$", order=0),
            ChatContentRegexRule(pattern="b$", action="replace", replacement="done", order=1),
        ]
        result = apply_content_regex_pipeline("a" * 35 + "b", rules, timeout_seconds=0.015)
        self.assertEqual([error["errorCode"] for error in result.errors], ["REGEX_TIMEOUT"])
        self.assertEqual(result.persisted_text, "a" * 35 + "done")

    def test_usage_does_not_charge_cached_tokens_twice(self):
        rate = {"inputPerMillion": 2, "cacheReadPerMillion": 0.2}
        for protocol in ("openai_compatible_chat", "openai_responses", "gemini_generate_content", "anthropic_messages"):
            with self.subTest(protocol=protocol), patch("app.services.pricing.resolve_pricing_rule", return_value=rate):
                usage = {"inputTokens": 100 if protocol == "anthropic_messages" else 1000, "cacheReadInputTokens": 900}
                result = estimate_cost_from_usage(usage, protocol=protocol, provider=None, resolved_model=None, requested_model=None)
                self.assertAlmostEqual(result["amount"], 0.00038)
                summary = summarize_ledger_events([{"protocol": protocol, "usage": usage}])
                self.assertAlmostEqual(summary["cacheHitRate"], 0.9)

    def test_graph_injection_depth_keeps_explicit_zero(self):
        for depth in (0, 1, 2):
            self.assertEqual(resolve_inject_depth(Chat(characterId="alice", overrides=ChatOverrides(knowledgeGraphInjectDepth=depth))), depth)

    def test_rich_paste_does_not_open_referenced_local_paths(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image:
            image.write(b"\x89PNG\r\n\x1a\nfixture")
        from pathlib import Path
        path = Path(image.name)
        self.addCleanup(path.unlink, missing_ok=True)
        result = clipboard.resolve_rich_paste(clipboard.ResolveRichPasteRequest(
            html=f'<p>Caption</p><img src="{path.as_uri()}">',
        ))
        self.assertEqual(result.text, "Caption")
        self.assertEqual(result.images, [])

    def test_sillytavern_worldbook_keywords_preserve_flags_and_ignore_only_invalid_keys(self):
        warnings = []
        book = build_worldbook("Fixture", {"character_book": {"entries": [{
            "keys": ["Dragon", "/wyrm/i", "/drake/", "/(/"],
            "content": "Description",
        }]}}, warnings)
        entry, = book.entries
        compiled = compile_timed_user_regex(entry.regex)
        for word in ("dragon", "WYRM", "drake"):
            self.assertIsNotNone(compiled.search(word))
        self.assertIsNone(compiled.search("DRAKE"))
        self.assertEqual(len(warnings), 1)


class LocalRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_middleware_rejects_untrusted_requests_before_reaching_routes(self):
        app = FastAPI()
        app.add_middleware(LocalRequestMiddleware, origins=["http://tavern.lan:9081"])

        @app.post("/api/{path:path}")
        def handler(path: str):
            return {"path": path}

        extension = "chrome-extension://" + "a" * 32
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:9091") as client:
            cases = [
                ("/api/settings", {"host": "untrusted.invalid"}, 400),
                ("/api/settings", {"origin": "https://untrusted.invalid"}, 403),
                ("/api/settings", {"origin": extension}, 403),
                ("/api/settings", {"origin": "http://127.0.0.1:9082"}, 200),
                ("/api/settings", {"host": "tavern.lan:9091", "origin": "http://tavern.lan:9081"}, 200),
                ("/api/import/janitor/pending", {"origin": extension}, 200),
            ]
            for path, headers, expected in cases:
                response = await client.post(path, headers=headers)
                self.assertEqual(response.status_code, expected, response.text)
