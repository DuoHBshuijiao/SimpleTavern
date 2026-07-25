"""TXT (Version 2) chat import should surface transcript row warnings instead of dropping them."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import zlib

from fastapi import UploadFile

from app.routes import import_export as ie
from app.schemas import CharacterCard, Settings


def _v2_text() -> str:
    return "\n".join([
        "SimpleTavern Chat Export",
        "Version: 2",
        "ChatId: c1",
        "Title: T",
        "IsGroup: false",
        "Participants: Hero",
        "",
        "[Message]",
        "role=user",
        "content:",
        "<<<",
        "hello",
        ">>>",
        "",
        "[Message]",
        "role=badrole",
        "name=x",
        "content:",
        "<<<",
        "oops",
        ">>>",
        "",
        "[Message]",
        "role=assistant",
        "name=Hero",
        "content:",
        "<<<",
        "hi",
        ">>>",
    ])


def test_parse_chat_text_v2_surfaces_transcript_warnings(monkeypatch):
    monkeypatch.setattr(ie, "list_characters", lambda: [CharacterCard(id="h1", name="Hero")])
    monkeypatch.setattr(ie, "load_settings", lambda: Settings())

    chat, warnings = ie._parse_chat_text(_v2_text())

    # 未知 role 的行应被跳过并产生结构化 warning
    assert any("badrole" in ie._warning_text(w) for w in warnings)
    assert any(isinstance(w, dict) and w.get("code") == "import_row_skipped" for w in warnings)
    # 仅保留合法的 user + assistant 两条
    assert len(chat.messages) == 2
    assert [m.role for m in chat.messages] == ["user", "assistant"]


def test_export_character_manifest_records_missing_worldbook(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.schemas import CharacterCard

    card = CharacterCard(id="c1", name="Hero", attachedWorldBookIds=["missing-wb"])
    monkeypatch.setattr(ie, "load_character", lambda _cid: card)

    def _missing(_wid):
        raise FileNotFoundError("gone")

    monkeypatch.setattr(ie, "load_worldbook", _missing)

    app = FastAPI()
    app.include_router(ie.router, prefix="/api")
    with TestClient(app) as client:
        resp = client.get("/api/characters/c1/export", params={"include_world_books": True})
    assert resp.status_code == 200
    import zipfile

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["partialSuccess"] is True
    assert any(w["code"] == "export_attachment_missing" for w in manifest["warnings"])
    assert manifest["exportedWorldBookIds"] == []


def _png_with_text_chunks(*chunks: tuple[str, str]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return len(data).to_bytes(4, "big") + kind + data + crc.to_bytes(4, "big")

    body = b"\x89PNG\r\n\x1a\n"
    for key, value in chunks:
        text_data = key.encode("latin-1") + b"\x00" + value.encode("latin-1")
        body += chunk(b"tEXt", text_data)
    body += chunk(b"IEND", b"")
    return body


def test_st_preview_persists_png_candidate_skip_warnings(monkeypatch):
    good = {
        "spec": "chara_card_v3",
        "data": {"name": "Hero", "description": "d", "first_mes": "hi"},
    }
    good_b64 = base64.b64encode(json.dumps(good).encode("utf-8")).decode("ascii")
    png = _png_with_text_chunks(
        ("ccv3", "%%%not-valid-base64%%%"),
        ("chara", good_b64),
    )

    async def _run() -> None:
        ie._sillytavern_pending_store.clear()
        preview = await ie.preview_sillytavern_import(
            UploadFile(filename="card.png", file=io.BytesIO(png)),
        )
        assert preview["partialSuccess"] is True
        assert any(w["code"] == "import_png_candidate_skipped" for w in preview["warnings"])
        pending_id = preview["pendingId"]
        stored = ie._sillytavern_pending_store[pending_id][1]
        assert stored["pngWarnings"]
        assert any(w["code"] == "import_png_candidate_skipped" for w in stored["pngWarnings"])

        monkeypatch.setattr(ie, "save_character", lambda card: card)
        monkeypatch.setattr(ie, "save_worldbook", lambda wb: wb)
        monkeypatch.setattr(ie, "save_avatar", lambda *_a, **_k: None)

        confirmed = await ie.confirm_sillytavern_import(
            ie.SillyTavernConfirmRequest(
                pendingId=pending_id,
                enableMvuCompatibility=False,
                mvuMode="regex",
            ),
        )
        assert any(
            isinstance(w, dict) and w.get("code") == "import_png_candidate_skipped"
            for w in confirmed["warnings"]
        )
        assert confirmed["partialSuccess"] is True

    asyncio.run(_run())
