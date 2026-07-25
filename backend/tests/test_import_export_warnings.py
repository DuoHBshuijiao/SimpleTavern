"""TXT (Version 2) chat import should surface transcript row warnings instead of dropping them."""

from __future__ import annotations

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
    import io
    import zipfile
    import json

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["partialSuccess"] is True
    assert any(w["code"] == "export_attachment_missing" for w in manifest["warnings"])
    assert manifest["exportedWorldBookIds"] == []

