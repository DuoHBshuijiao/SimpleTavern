from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from urllib.parse import quote
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.schemas import Chat, ChatMessage, CharacterCard, Settings
from app.storage import (
    avatar_path,
    avatars_dir,
    characters_dir,
    chats_dir,
    load_character,
    load_chat,
    load_settings,
    save_character,
    save_chat,
    save_settings,
)

router = APIRouter(tags=["import_export"])


def _sanitize_filename(name: str, fallback: str) -> str:
    if not name:
        return fallback
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return safe or fallback


def _content_disposition(filename: str) -> str:
    ascii_fallback = re.sub(r"[^\x20-\x7E]+", "_", filename).strip() or "download"
    encoded = quote(filename)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _resolve_pure_ai_mode(settings: Settings, chat: Chat) -> bool:
    if getattr(chat, "overrides", None) is not None and getattr(chat.overrides, "pureAiMode", None) is not None:
        return bool(chat.overrides.pureAiMode)
    return bool(getattr(settings, "pureAiMode", False))


def _build_user_persona_prompt(settings: Settings) -> str | None:
    if not settings.selectedPersonaId or not settings.userPersonas:
        return None
    selected = next((p for p in settings.userPersonas if p.id == settings.selectedPersonaId), None)
    if not selected:
        return None
    parts: list[str] = []
    if selected.name and selected.name.strip():
        parts.append(f"user姓名：{selected.name.strip()}")
    if selected.description and selected.description.strip():
        parts.append(f"User简介：\n{selected.description.strip()}")
    return "\n".join(parts) if parts else None


def _build_single_system_prompt(chat: Chat, settings: Settings) -> str:
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)

    if not _resolve_pure_ai_mode(settings, chat):
        persona_prompt = _build_user_persona_prompt(settings)
        if persona_prompt:
            prompt_parts.append(persona_prompt)

    try:
        character = load_character(chat.characterId)
        character_parts: list[str] = []
        if character.name and character.name.strip():
            character_parts.append(f"char姓名：{character.name.strip()}")
        if character.personality and character.personality.strip():
            character_parts.append(f"Personality：\n{character.personality.strip()}")
        if character.scenario and character.scenario.strip():
            character_parts.append(f"Scenario：\n{character.scenario.strip()}")
        if character.systemPrompt and character.systemPrompt.strip():
            character_parts.append(character.systemPrompt.strip())
        if character_parts:
            prompt_parts.append("\n\n".join(character_parts))
    except FileNotFoundError:
        pass

    if chat.overrides.prompt:
        prompt_parts.append(chat.overrides.prompt)

    return "\n\n".join([p for p in prompt_parts if p.strip()])


def _pick_group_export_character(chat: Chat) -> str:
    for m in reversed(chat.messages):
        if m.role == "assistant" and m.characterId:
            return m.characterId
    for m in reversed(chat.messages):
        if m.characterId:
            return m.characterId
    if chat.memberIds:
        return chat.memberIds[-1]
    return chat.characterId


def _build_group_system_prompt(chat: Chat, settings: Settings, character_id: str) -> str:
    prompt_parts: list[str] = []
    if settings.prompts.globalSystem:
        prompt_parts.append(settings.prompts.globalSystem)

    if not _resolve_pure_ai_mode(settings, chat):
        persona_prompt = _build_user_persona_prompt(settings)
        if persona_prompt:
            prompt_parts.append(persona_prompt)

    all_characters = []
    for member_id in chat.memberIds:
        try:
            member_char = load_character(member_id)
            all_characters.append(member_char)
        except FileNotFoundError:
            continue

    group_context_parts = ["这是一个群聊场景，参与者包括："]
    for i, char in enumerate(all_characters):
        group_context_parts.append(f"{i+1}. {char.name}")
    prompt_parts.append("\n".join(group_context_parts))

    member_settings = chat.memberSettings.get(character_id)
    include_personality = True if member_settings is None else bool(getattr(member_settings, "includePersonality", True))
    include_scenario = True if member_settings is None else bool(getattr(member_settings, "includeScenario", True))

    try:
        character = load_character(character_id)
        character_parts: list[str] = []
        character_parts.append(f"你现在扮演的角色是：{character.name}")
        if include_personality and character.personality and character.personality.strip():
            character_parts.append(f"Personality：\n{character.personality.strip()}")
        if include_scenario and character.scenario and character.scenario.strip():
            character_parts.append(f"Scenario：\n{character.scenario.strip()}")
        if character.systemPrompt and character.systemPrompt.strip():
            character_parts.append(character.systemPrompt.strip())
        if character_parts:
            prompt_parts.append("\n\n".join(character_parts))
    except FileNotFoundError:
        pass

    if chat.overrides.prompt:
        prompt_parts.append(chat.overrides.prompt)

    return "\n\n".join([p for p in prompt_parts if p.strip()])


def _build_system_prompt_for_chat(chat: Chat, settings: Settings) -> tuple[str, str | None]:
    if not chat.isGroup:
        return _build_single_system_prompt(chat, settings), None
    last_speaker_id = _pick_group_export_character(chat)
    return _build_group_system_prompt(chat, settings, last_speaker_id), last_speaker_id


def _chat_export_participants(chat: Chat) -> str:
    if not chat.isGroup:
        try:
            character = load_character(chat.characterId)
            return character.name or "角色"
        except FileNotFoundError:
            return "角色"
    names: list[str] = []
    for member_id in chat.memberIds:
        try:
            member = load_character(member_id)
            if member.name:
                names.append(member.name)
        except FileNotFoundError:
            continue
    return "、".join(names) or "群聊"


def _format_message_block(m: ChatMessage) -> list[str]:
    lines = ["[Message]"]
    lines.append(f"id={m.id}")
    lines.append(f"ts={m.ts}")
    lines.append(f"role={m.role}")
    lines.append(f"characterId={m.characterId or ''}")
    lines.append(f"senderName={m.senderName or ''}")
    lines.append(f"senderAvatar={m.senderAvatar or ''}")
    lines.append("content:")
    lines.append("<<<")
    lines.extend((m.content or "").splitlines() or [""])
    lines.append(">>>")
    return lines


def _export_chat_text(chat: Chat, system_prompt: str, last_speaker_id: str | None) -> str:
    lines: list[str] = []
    lines.append("SimpleTavern Chat Export")
    lines.append("Version: 1")
    lines.append(f"ChatId: {chat.id}")
    lines.append(f"Title: {chat.title}")
    lines.append(f"CharacterId: {chat.characterId}")
    lines.append(f"IsGroup: {'true' if chat.isGroup else 'false'}")
    if chat.memberIds:
        lines.append(f"MemberIds: {','.join(chat.memberIds)}")
    lines.append(f"GroupDelay: {chat.groupDelay}")
    if last_speaker_id:
        lines.append(f"LastSpeakerId: {last_speaker_id}")
    lines.append("SystemPrompt:")
    lines.append("<<<")
    lines.extend(system_prompt.splitlines() or [""])
    lines.append(">>>")
    lines.append("")
    for m in chat.messages:
        lines.extend(_format_message_block(m))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@router.get("/chats/{chat_id}/export")
def export_chat(chat_id: str, format: str = Query("txt")) -> Response:
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    settings = load_settings()
    system_prompt, last_speaker_id = _build_system_prompt_for_chat(chat, settings)
    participants = _chat_export_participants(chat)
    export_date = datetime.now().astimezone()
    date_str = f"{export_date.year}/{export_date.month}/{export_date.day}"
    base_name = _sanitize_filename(f"{participants} - {date_str}", "chat")

    if format.lower() == "json":
        export_obj = {
            "type": "chat_export",
            "version": 1,
            "systemPrompt": system_prompt,
            "lastSpeakerCharacterId": last_speaker_id,
            "chat": chat.model_dump(mode="json"),
        }
        content = json.dumps(export_obj, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": _content_disposition(f"{base_name}.json")},
        )

    if format.lower() != "txt":
        raise HTTPException(status_code=400, detail="unsupported format")

    content = _export_chat_text(chat, system_prompt, last_speaker_id)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(f"{base_name}.txt")},
    )


@router.get("/settings/backup")
def backup_settings(scope: str = Query("basic")) -> Response:
    settings = load_settings()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("settings.json", json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2))
        for persona in settings.userPersonas:
            if not persona.avatar:
                continue
            p = avatar_path(persona.avatar)
            if p.exists():
                zf.write(p, arcname=f"avatars/{p.name}")
        if scope not in ("basic", "with_characters", "with_chats"):
            raise HTTPException(status_code=400, detail="unsupported scope")
        if scope in ("with_characters", "with_chats"):
            for p in characters_dir().glob("*.json"):
                zf.write(p, arcname=f"characters/{p.name}")
            for p in characters_dir().glob("*.json"):
                try:
                    card = CharacterCard.model_validate(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
                if card.avatar:
                    avatar_file = avatar_path(card.avatar)
                    if avatar_file.exists():
                        zf.write(avatar_file, arcname=f"avatars/{avatar_file.name}")
        if scope == "with_chats":
            for p in chats_dir().rglob("*.json"):
                rel = p.relative_to(chats_dir())
                zf.write(p, arcname=f"chats/{rel.as_posix()}")
    buffer.seek(0)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition("settings-backup.zip")},
    )


def _parse_character_text(content: str) -> CharacterCard:
    def pick_section(label: str) -> str:
        pattern = rf"【{re.escape(label)}】\n(.*?)(?:\n【|$)"
        match = re.search(pattern, content, re.S)
        if not match:
            return ""
        return match.group(1).strip()

    name_match = re.search(r"角色名称:\s*(.+)", content)
    name = name_match.group(1).strip() if name_match else "新角色"
    now = None
    try:
        created_match = re.search(r"创建时间:\s*(.+)", content)
        if created_match:
            now = created_match.group(1).strip()
    except Exception:
        now = None

    card = CharacterCard(
        name=name,
        description=pick_section("简介"),
        personality=pick_section("Personality（性格/外貌）"),
        scenario=pick_section("Scenario（情景/世界观）"),
        systemPrompt=pick_section("系统提示词"),
        firstMessage=pick_section("首句"),
        exampleDialogue=pick_section("示例对话"),
    )
    if now:
        card.createdAt = now
    return card


def _parse_chat_text(content: str) -> Chat:
    lines = content.splitlines()
    idx = 0
    header: dict[str, Any] = {}
    messages: list[ChatMessage] = []
    system_prompt = ""

    def read_block(start_index: int) -> tuple[str, int]:
        if start_index >= len(lines) or lines[start_index].strip() != "<<<":
            return "", start_index
        buf: list[str] = []
        i = start_index + 1
        while i < len(lines):
            if lines[i].strip() == ">>>":
                return "\n".join(buf).strip(), i + 1
            buf.append(lines[i])
            i += 1
        return "\n".join(buf).strip(), i

    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith("SystemPrompt:"):
            system_prompt, idx = read_block(idx + 1)
            header["systemPrompt"] = system_prompt
            continue
        if line == "[Message]":
            msg_data: dict[str, Any] = {}
            idx += 1
            while idx < len(lines):
                msg_line = lines[idx].strip()
                if msg_line == "content:":
                    content_block, idx = read_block(idx + 1)
                    msg_data["content"] = content_block
                    break
                if "=" in msg_line:
                    k, v = msg_line.split("=", 1)
                    msg_data[k] = v
                idx += 1
            messages.append(ChatMessage.model_validate(msg_data))
            idx += 1
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            header[k.strip()] = v.strip()
        idx += 1

    if not header.get("CharacterId"):
        raise HTTPException(status_code=400, detail="missing CharacterId in text import")

    chat_data = {
        "title": header.get("Title") or "新对话",
        "characterId": header.get("CharacterId"),
        "isGroup": header.get("IsGroup", "false").lower() == "true",
        "memberIds": [m for m in (header.get("MemberIds") or "").split(",") if m],
        "groupDelay": int(header.get("GroupDelay") or 1500),
        "messages": [m.model_dump(mode="json") for m in messages],
    }
    if header.get("ChatId"):
        chat_data["id"] = header.get("ChatId")
    return Chat.model_validate(chat_data)


def _import_from_json(raw: Any) -> dict[str, Any]:
    imported: list[str] = []
    warnings: list[str] = []

    if isinstance(raw, dict) and raw.get("type") == "chat_export":
        raw = raw.get("chat")

    if isinstance(raw, dict) and ("llm" in raw or "prompts" in raw or "apiPresets" in raw):
        settings = Settings.model_validate(raw)
        save_settings(settings)
        imported.append("settings")
        return {"imported": imported, "warnings": warnings}

    if isinstance(raw, dict) and ("messages" in raw and "characterId" in raw):
        chat = Chat.model_validate(raw)
        save_chat(chat)
        imported.append("chat")
        return {"imported": imported, "warnings": warnings}

    if isinstance(raw, dict) and ("name" in raw and ("personality" in raw or "systemPrompt" in raw)):
        card = CharacterCard.model_validate(raw)
        save_character(card)
        imported.append("character")
        return {"imported": imported, "warnings": warnings}

    raise HTTPException(status_code=400, detail="unrecognized json format")


def _import_from_zip(payload: bytes) -> dict[str, Any]:
    imported: list[str] = []
    warnings: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        if "settings.json" in zf.namelist():
            raw_settings = json.loads(zf.read("settings.json").decode("utf-8"))
            settings = Settings.model_validate(raw_settings)
            save_settings(settings)
            imported.append("settings")
        else:
            warnings.append("settings.json not found in zip")

        for name in zf.namelist():
            if not name.startswith("avatars/"):
                continue
            filename = name.split("/", 1)[-1]
            if not filename:
                continue
            data = zf.read(name)
            avatars_dir().mkdir(parents=True, exist_ok=True)
            avatar_path(filename).write_bytes(data)
        for name in zf.namelist():
            if name.startswith("characters/") and name.endswith(".json"):
                raw = json.loads(zf.read(name).decode("utf-8"))
                card = CharacterCard.model_validate(raw)
                save_character(card)
                if "character" not in imported:
                    imported.append("character")
        for name in zf.namelist():
            if name.startswith("chats/") and name.endswith(".json"):
                raw = json.loads(zf.read(name).decode("utf-8"))
                chat = Chat.model_validate(raw)
                save_chat(chat)
                if "chat" not in imported:
                    imported.append("chat")
    return {"imported": imported, "warnings": warnings}


@router.post("/import")
async def import_data(file: UploadFile = File(...)) -> dict:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty file")

    filename = (file.filename or "").lower()
    try:
        if payload[:4] == b"PK\x03\x04":
            result = _import_from_zip(payload)
            return {"ok": True, **result}
        if filename.endswith(".json") or (file.content_type and "json" in file.content_type):
            raw = json.loads(payload.decode("utf-8"))
            result = _import_from_json(raw)
            return {"ok": True, **result}
        text = payload.decode("utf-8")
        if "SimpleTavern Chat Export" in text or "[Message]" in text:
            chat = _parse_chat_text(text)
            save_chat(chat)
            return {"ok": True, "imported": ["chat"], "warnings": []}
        if "角色名称" in text or "【简介】" in text:
            card = _parse_character_text(text)
            save_character(card)
            return {"ok": True, "imported": ["character"], "warnings": []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    raise HTTPException(status_code=400, detail="unsupported file format")
