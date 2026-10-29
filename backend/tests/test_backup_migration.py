import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi import HTTPException
from app.routes import import_export
from app.schemas import Settings


class BackupMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": str(self.root)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.settings = patch.object(import_export, "load_settings", return_value=Settings())
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.payloads = {
            "characters/hero.json": b'{"id":"hero","name":"Hero"}',
            "worldbooks/lore.json": b'{"id":"lore","name":"Lore"}',
            "chats/hero/chat/chat.json": b'{"id":"chat","messages":[]}',
            "chats/hero/chat/knowledge_graph.json": b'{"entities":[],"relations":[]}',
            "chats/hero/chat/images/picture.png": b"image-fixture",
            "chats/hero/chat/attachments/document.pdf": b"document-fixture",
            "chats/hero/chat/long_term_memory.txt": "长期记忆".encode(),
            "assistant_settings.json": b'{}',
            "assistant_chat.json": b'{"messages":[]}',
            "ai_workspace/notes.md": b"workspace notes",
            "ai_workspace/ingest/assistant_chat/main/source.bin": b"original ingest bytes",
            "usage/2026-10.jsonl": b'{"eventId":"event-1"}\n',
            "usage/repair.jsonl": b'{"eventId":"repair-1"}\n',
        }
        for name, data in self.payloads.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def archive(self, scope):
        response = import_export.backup_settings(scope)
        return zipfile.ZipFile(io.BytesIO(response.body))

    def test_full_backup_preserves_migration_files_byte_for_byte(self):
        with self.archive("with_chats") as archive:
            self.assertIn("settings.json", archive.namelist())
            for name, expected in self.payloads.items():
                self.assertEqual(expected, archive.read(name), name)

    def test_basic_and_character_scopes_keep_their_existing_boundaries(self):
        with self.archive("basic") as archive:
            self.assertEqual({"settings.json"}, set(archive.namelist()))
        with self.archive("with_characters") as archive:
            self.assertEqual({"settings.json", "characters/hero.json", "worldbooks/lore.json"}, set(archive.namelist()))

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.archive("unknown")
        self.assertEqual(400, error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
