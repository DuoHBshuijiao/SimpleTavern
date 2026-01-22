from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import portalocker

from datetime import datetime

from app.schemas import AssistantChat, AssistantSettings, Chat, CharacterCard, Settings


def _repo_root() -> Path:
    # backend/app/storage.py -> backend/app -> backend -> repoRoot
    return Path(__file__).resolve().parents[2]


def _data_dir() -> Path:
    return _repo_root() / "data"


def _characters_dir() -> Path:
    return _data_dir() / "characters"


def _chats_dir() -> Path:
    return _data_dir() / "chats"


def _avatars_dir() -> Path:
    return _data_dir() / "avatars"


def _ai_workspace_dir() -> Path:
    return _data_dir() / "ai_workspace"


def _settings_path() -> Path:
    return _data_dir() / "settings.json"


def _assistant_settings_path() -> Path:
    return _data_dir() / "assistant_settings.json"


def _assistant_chat_path() -> Path:
    return _data_dir() / "assistant_chat.json"


def _assistant_workspace_chat_path() -> Path:
    return _ai_workspace_dir() / "assistant_workspace_chat.json"

CHAT_RECORD_FILENAME = "chat.json"
CHAT_MEMORY_FILENAME = "chat_memory.json"
ASSISTANT_CHAT_FILENAME = "assistant_chat.json"
ASSISTANT_WORKSPACE_CHAT_FILENAME = "assistant_workspace_chat.json"


DEFAULT_ASSISTANT_PROMPT = (
    "你是“聊天助理（角色卡创建助手 + 会话辅助）”。\n"
    "目标：只在当前会话内提供帮助，协助用户完善角色卡字段、解释当前对话与长期记忆，并在合适时机生成角色卡 JSON。\n"
    "范围：仅使用当前会话的数据，不访问或猜测其他会话内容。\n"
    "工具使用规范（仅在需要时调用）：\n"
    "- read_file/create_file/write_file/delete_file：必须使用 data/ai_workspace/ 下的相对路径，路径不允许自行杜撰或越界。\n"
    "- read_chat_json：无需参数。\n"
    "- read_chat_memory：无需参数。\n"
    "- list_participants：无需参数。\n"
    "- read_character_card：只传入一个字符串参数 characterId（从 list_participants 获得）。\n"
    "- write_chat_memory：只传入一个字符串参数 content；该内容会整段覆盖当前长期记忆（不是追加）。仅在用户明确要求“写入/更新/保存长期记忆”时使用。\n"
    "- create_file/write_file：参数仅为 path 与 content（均为字符串）。\n"
    "- delete_file/read_file：参数仅为 path（字符串）。\n"
    "重要规则：\n"
    "1) 不要声称已读取/写入文件，除非实际调用了对应工具。\n"
    "2) 不要使用绝对路径或越出 data/ai_workspace/ 的路径。\n"
    "3) 工具结果出现不确定时，先向用户澄清再行动。\n"
    "生成角色卡流程：\n"
    "1) 组织完整角色卡 JSON（包含 version、id、name、description、personality、scenario、firstMessage、"
    "exampleDialogue、systemPrompt、avatar（为空，不要填写虚假地址）、createdAt、updatedAt）。\n"
    "2) 【重要】exampleDialogue 必须是纯字符串而非数组；用换行分隔，如：\n"
    "   \"exampleDialogue\": \"用户：你好\\n角色：你好呀！\\n用户：今天怎么样？\\n角色：很开心呢！\"\n"
    "3) 使用 write_file 写入 data/ai_workspace/character_card.json。\n"
    "4) 写入后用简短文字告知已生成并可继续调整；不要在回复中重复输出整段 JSON。\n"
)


def ensure_data_initialized() -> None:
    _data_dir().mkdir(parents=True, exist_ok=True)
    _characters_dir().mkdir(parents=True, exist_ok=True)
    _chats_dir().mkdir(parents=True, exist_ok=True)
    _avatars_dir().mkdir(parents=True, exist_ok=True)
    _ai_workspace_dir().mkdir(parents=True, exist_ok=True)

    if not _settings_path().exists():
        settings = Settings()
        write_json(_settings_path(), settings.model_dump(mode="json"))
    if not _assistant_settings_path().exists():
        settings = AssistantSettings(prompt=DEFAULT_ASSISTANT_PROMPT)
        write_json(_assistant_settings_path(), settings.model_dump(mode="json"))
    if not _assistant_chat_path().exists():
        chat = AssistantChat()
        write_json(_assistant_chat_path(), chat.model_dump(mode="json"))


@dataclass(frozen=True)
class LockedFile:
    lock_path: Path
    lock_handle: Any

    def __enter__(self) -> "LockedFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            portalocker.unlock(self.lock_handle)
        finally:
            self.lock_handle.close()


def _lock_for(target: Path) -> LockedFile:
    # 单用户应用也可能因前端并发请求导致短暂并发写；用 lock 文件规避写入撕裂。
    lock_path = Path(str(target) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    portalocker.lock(fh, portalocker.LOCK_EX)
    return LockedFile(lock_path=lock_path, lock_handle=fh)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with _lock_for(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    with _lock_for(path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)


def list_json_files(dir_path: Path) -> list[Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() == ".json"])


# ---------- Settings ----------


def load_settings() -> Settings:
    raw = read_json(_settings_path())
    return Settings.model_validate(raw)


def save_settings(settings: Settings) -> Settings:
    settings.updatedAt = datetime.now().astimezone().isoformat()
    write_json(_settings_path(), settings.model_dump(mode="json"))
    return settings


def settings_path() -> Path:
    return _settings_path()


def assistant_settings_path() -> Path:
    return _assistant_settings_path()


def assistant_chat_path() -> Path:
    return _assistant_chat_path()


def assistant_workspace_chat_path() -> Path:
    return _assistant_workspace_chat_path()


def assistant_chat_path_for_chat(chat_id: str) -> Path:
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        raise FileNotFoundError(chat_id)
    _, character_id = found
    return chat_folder(character_id, chat_id) / ASSISTANT_CHAT_FILENAME


def characters_dir() -> Path:
    return _characters_dir()


def chats_dir() -> Path:
    return _chats_dir()


def ai_workspace_dir() -> Path:
    return _ai_workspace_dir()


# ---------- Characters ----------


def character_path(character_id: str) -> Path:
    return _characters_dir() / f"{character_id}.json"


def list_characters() -> list[CharacterCard]:
    out: list[CharacterCard] = []
    for p in list_json_files(_characters_dir()):
        try:
            out.append(CharacterCard.model_validate(read_json(p)))
        except Exception:
            # 本地文件可能被用户手改；坏文件不阻断列表
            continue
    out.sort(key=lambda c: c.updatedAt, reverse=True)
    return out


def load_character(character_id: str) -> CharacterCard:
    return CharacterCard.model_validate(read_json(character_path(character_id)))


def save_character(card: CharacterCard) -> CharacterCard:
    write_json(character_path(card.id), card.model_dump(mode="json"))
    return card


def delete_character(character_id: str, delete_related_chats: bool = True) -> None:
    p = character_path(character_id)
    if p.exists():
        with _lock_for(p):
            p.unlink(missing_ok=True)
    
    # 同步删除该角色关联的所有会话
    if delete_related_chats:
        delete_chats_by_character(character_id)


# ---------- Chats ----------


def chat_dir(character_id: str) -> Path:
    return _chats_dir() / character_id


def chat_folder(character_id: str, chat_id: str) -> Path:
    return chat_dir(character_id) / chat_id


def chat_record_path(character_id: str, chat_id: str) -> Path:
    return chat_folder(character_id, chat_id) / CHAT_RECORD_FILENAME


def chat_memory_path(character_id: str, chat_id: str) -> Path:
    return chat_folder(character_id, chat_id) / CHAT_MEMORY_FILENAME


def legacy_chat_path(character_id: str, chat_id: str) -> Path:
    return chat_dir(character_id) / f"{chat_id}.json"


def _attach_chat_memory(chat: Chat) -> None:
    try:
        memory = load_chat_memory(chat.characterId, chat.id)
    except FileNotFoundError:
        memory = None
    if memory is not None:
        chat.overrides.longTermMemory = memory
    else:
        chat.overrides.longTermMemory = None


def _load_chat_from_path(path: Path, character_id: str) -> Chat | None:
    try:
        chat = Chat.model_validate(read_json(path))
    except Exception:
        return None
    if chat.characterId != character_id:
        chat.characterId = character_id
    _attach_chat_memory(chat)
    return chat


def list_chats(character_id: str) -> list[Chat]:
    out: list[Chat] = []
    base = chat_dir(character_id)
    if not base.exists():
        return out
    seen_ids: set[str] = set()

    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        record_path = entry / CHAT_RECORD_FILENAME
        if record_path.exists():
            chat = _load_chat_from_path(record_path, character_id)
            if chat is not None:
                out.append(chat)
                seen_ids.add(chat.id)

    for p in list_json_files(base):
        if p.name == CHAT_MEMORY_FILENAME:
            continue
        if p.stem in seen_ids:
            continue
        if (base / p.stem / CHAT_RECORD_FILENAME).exists():
            continue
        chat = _load_chat_from_path(p, character_id)
        if chat is not None:
            out.append(chat)

    out.sort(key=lambda c: c.updatedAt, reverse=True)
    return out


def _find_chat_path_by_id(chat_id: str) -> tuple[Path, str] | None:
    # 无 DB：扫描所有角色目录以定位 chatId
    base = _chats_dir()
    if not base.exists():
        return None
    for character_dir in base.iterdir():
        if not character_dir.is_dir():
            continue
        record_path = character_dir / chat_id / CHAT_RECORD_FILENAME
        if record_path.exists():
            return record_path, character_dir.name
        legacy_path = character_dir / f"{chat_id}.json"
        if legacy_path.exists():
            return legacy_path, character_dir.name
    return None


def load_chat(chat_id: str) -> Chat:
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        raise FileNotFoundError(chat_id)
    p, character_id = found
    chat = _load_chat_from_path(p, character_id)
    if chat is None:
        raise FileNotFoundError(chat_id)
    return chat


def save_chat(chat: Chat) -> Chat:
    memory = getattr(chat.overrides, "longTermMemory", None)
    if memory is not None and memory.strip():
        save_chat_memory(chat.characterId, chat.id, memory)
    else:
        delete_chat_memory(chat.characterId, chat.id)

    p = chat_record_path(chat.characterId, chat.id)
    legacy = legacy_chat_path(chat.characterId, chat.id)
    payload = chat.model_dump(mode="json")
    if "overrides" in payload:
        payload["overrides"].pop("longTermMemory", None)
    write_json(p, payload)
    if legacy.exists():
        with _lock_for(legacy):
            legacy.unlink(missing_ok=True)
    return chat


def load_chat_memory(character_id: str, chat_id: str) -> str | None:
    path = chat_memory_path(character_id, chat_id)
    if not path.exists():
        raise FileNotFoundError(str(path))
    raw = read_json(path)
    if isinstance(raw, dict):
        content = raw.get("longTermMemory", None)
        if content is None:
            content = raw.get("content", None)
        return content
    if isinstance(raw, str):
        return raw
    return None


def save_chat_memory(character_id: str, chat_id: str, content: str) -> None:
    path = chat_memory_path(character_id, chat_id)
    write_json(path, {"longTermMemory": content})


def delete_chat_memory(character_id: str, chat_id: str) -> None:
    path = chat_memory_path(character_id, chat_id)
    if path.exists():
        with _lock_for(path):
            path.unlink(missing_ok=True)


def delete_chat(chat_id: str) -> None:
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        return
    p, character_id = found
    with _lock_for(p):
        p.unlink(missing_ok=True)
    delete_chat_memory(character_id, chat_id)
    chat_dir_path = chat_folder(character_id, chat_id)
    if chat_dir_path.exists():
        try:
            chat_dir_path.rmdir()
        except OSError:
            pass


def delete_chats_by_character(character_id: str) -> None:
    """删除指定角色的所有会话"""
    char_chat_dir = chat_dir(character_id)
    if not char_chat_dir.exists():
        return
    for entry in char_chat_dir.iterdir():
        if entry.is_dir():
            for p in sorted(entry.rglob("*"), key=lambda x: len(str(x)), reverse=True):
                try:
                    if p.is_file():
                        with _lock_for(p):
                            p.unlink(missing_ok=True)
                    elif p.is_dir():
                        p.rmdir()
                except Exception:
                    continue
        elif entry.is_file() and entry.suffix.lower() == ".json":
            with _lock_for(entry):
                entry.unlink(missing_ok=True)
    # 尝试删除空目录
    try:
        char_chat_dir.rmdir()
    except OSError:
        pass


def list_group_chats() -> list[Chat]:
    """列出所有群聊 (isGroup=True)"""
    out: list[Chat] = []
    base = _chats_dir()
    if not base.exists():
        return out
    for character_dir in base.iterdir():
        if not character_dir.is_dir():
            continue
        for chat in list_chats(character_dir.name):
            if chat.isGroup:
                out.append(chat)
    out.sort(key=lambda c: c.updatedAt, reverse=True)
    return out


# ---------- Avatars ----------


def avatars_dir() -> Path:
    return _avatars_dir()


def avatar_path(filename: str) -> Path:
    return _avatars_dir() / filename


def save_avatar(filename: str, data: bytes) -> str:
    """保存头像并返回文件名"""
    p = avatar_path(filename)
    p.write_bytes(data)
    return filename


def delete_avatar(filename: str) -> None:
    """删除头像文件"""
    if not filename:
        return
    p = avatar_path(filename)
    if p.exists():
        p.unlink(missing_ok=True)


# ---------- Assistant ----------


def _assistant_chat_has_missing_ids(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    messages = raw.get("messages")
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if isinstance(msg, dict) and not msg.get("id"):
            return True
    return False


def load_assistant_settings() -> AssistantSettings:
    raw = read_json(_assistant_settings_path())
    return AssistantSettings.model_validate(raw)


def save_assistant_settings(settings: AssistantSettings) -> AssistantSettings:
    write_json(_assistant_settings_path(), settings.model_dump(mode="json"))
    return settings


def load_assistant_chat() -> AssistantChat:
    path = _assistant_chat_path()
    raw = read_json(path)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
        write_json(path, chat.model_dump(mode="json"))
    return chat


def load_assistant_workspace_chat() -> AssistantChat:
    path = _assistant_workspace_chat_path()
    if not path.exists():
        chat = AssistantChat()
        write_json(path, chat.model_dump(mode="json"))
        return chat
    raw = read_json(path)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
        write_json(path, chat.model_dump(mode="json"))
    return chat


def load_assistant_chat_for_chat(chat_id: str) -> AssistantChat:
    path = assistant_chat_path_for_chat(chat_id)
    if not path.exists():
        chat = AssistantChat()
        write_json(path, chat.model_dump(mode="json"))
        return chat
    raw = read_json(path)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
        write_json(path, chat.model_dump(mode="json"))
    return chat


def save_assistant_chat(chat: AssistantChat) -> AssistantChat:
    write_json(_assistant_chat_path(), chat.model_dump(mode="json"))
    return chat


def save_assistant_workspace_chat(chat: AssistantChat) -> AssistantChat:
    write_json(_assistant_workspace_chat_path(), chat.model_dump(mode="json"))
    return chat


def save_assistant_chat_for_chat(chat_id: str, chat: AssistantChat) -> AssistantChat:
    path = assistant_chat_path_for_chat(chat_id)
    write_json(path, chat.model_dump(mode="json"))
    return chat


def clear_assistant_chat() -> None:
    chat = AssistantChat()
    write_json(_assistant_chat_path(), chat.model_dump(mode="json"))


def clear_assistant_workspace_chat() -> None:
    chat = AssistantChat()
    write_json(_assistant_workspace_chat_path(), chat.model_dump(mode="json"))


def delete_assistant_workspace_chat() -> None:
    path = _assistant_workspace_chat_path()
    if path.exists():
        with _lock_for(path):
            path.unlink(missing_ok=True)


def clear_assistant_chat_for_chat(chat_id: str) -> None:
    chat = AssistantChat()
    path = assistant_chat_path_for_chat(chat_id)
    write_json(path, chat.model_dump(mode="json"))


def clear_ai_workspace() -> None:
    base = _ai_workspace_dir()
    if not base.exists():
        return
    for p in sorted(base.rglob("*"), key=lambda x: len(str(x)), reverse=True):
        try:
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                p.rmdir()
        except Exception:
            continue


