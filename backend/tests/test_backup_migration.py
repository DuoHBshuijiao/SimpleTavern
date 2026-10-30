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

    def restore_into_new_data_dir(self, payload):
        target = tempfile.TemporaryDirectory()
        self.addCleanup(target.cleanup)
        root = Path(target.name)
        with patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": str(root)}):
            result = import_export._import_from_zip(payload)
        return root, result

    def test_full_backup_restores_every_migration_file(self):
        payload = import_export.backup_settings("with_chats").body
        root, result = self.restore_into_new_data_dir(payload)
        self.assertEqual([], result["warnings"])
        for name, expected in self.payloads.items():
            if name.endswith("/chat.json") or name.startswith(("characters/", "worldbooks/")):
                continue  # rewritten by their save functions
            self.assertEqual(expected, (root / name).read_bytes(), name)
        self.assertTrue((root / "chats/hero/chat/chat.json").is_file())
        self.assertTrue((root / "usage/usage_index.json").is_file())

    def test_usage_import_merges_by_event_id(self):
        payload = import_export.backup_settings("with_chats").body
        target = tempfile.TemporaryDirectory()
        self.addCleanup(target.cleanup)
        root = Path(target.name)
        (root / "usage").mkdir()
        (root / "usage/2026-10.jsonl").write_bytes(b'{"eventId":"local-1"}\n{"eventId":"event-1"}\n')
        with patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": str(root)}):
            import_export._import_from_zip(payload)
            import_export._import_from_zip(payload)
        lines = (root / "usage/2026-10.jsonl").read_bytes().splitlines()
        self.assertEqual([b'{"eventId":"local-1"}', b'{"eventId":"event-1"}'], lines)

    def test_paths_outside_their_folder_are_skipped(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("chats/hero/chat/chat.json", '{"id":"chat","messages":[]}')
            zf.writestr("chats/hero/chat/../../../escaped.txt", "x")
            zf.writestr("ai_workspace/../escaped.txt", "x")
        root, result = self.restore_into_new_data_dir(buffer.getvalue())
        self.assertFalse((root / "escaped.txt").exists())
        self.assertFalse((root.parent / "escaped.txt").exists())
        self.assertEqual(2, len(result["warnings"]))

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            self.archive("unknown")
        self.assertEqual(400, error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
