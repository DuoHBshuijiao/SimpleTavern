from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import portalocker

from datetime import datetime

from app.schemas import Chat, CharacterCard, Settings


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


def _settings_path() -> Path:
    return _data_dir() / "settings.json"


def ensure_data_initialized() -> None:
    _data_dir().mkdir(parents=True, exist_ok=True)
    _characters_dir().mkdir(parents=True, exist_ok=True)
    _chats_dir().mkdir(parents=True, exist_ok=True)
    _avatars_dir().mkdir(parents=True, exist_ok=True)

    if not _settings_path().exists():
        settings = Settings()
        write_json(_settings_path(), settings.model_dump(mode="json"))


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


def chat_path(character_id: str, chat_id: str) -> Path:
    return chat_dir(character_id) / f"{chat_id}.json"


def list_chats(character_id: str) -> list[Chat]:
    out: list[Chat] = []
    for p in list_json_files(chat_dir(character_id)):
        try:
            out.append(Chat.model_validate(read_json(p)))
        except Exception:
            continue
    out.sort(key=lambda c: c.updatedAt, reverse=True)
    return out


def _find_chat_path_by_id(chat_id: str) -> Path | None:
    # 无 DB：扫描所有角色目录以定位 chatId
    base = _chats_dir()
    if not base.exists():
        return None
    for character_dir in base.iterdir():
        if not character_dir.is_dir():
            continue
        p = character_dir / f"{chat_id}.json"
        if p.exists():
            return p
    return None


def load_chat(chat_id: str) -> Chat:
    p = _find_chat_path_by_id(chat_id)
    if p is None:
        raise FileNotFoundError(chat_id)
    return Chat.model_validate(read_json(p))


def save_chat(chat: Chat) -> Chat:
    p = chat_path(chat.characterId, chat.id)
    write_json(p, chat.model_dump(mode="json"))
    return chat


def delete_chat(chat_id: str) -> None:
    p = _find_chat_path_by_id(chat_id)
    if p is None:
        return
    with _lock_for(p):
        p.unlink(missing_ok=True)


def delete_chats_by_character(character_id: str) -> None:
    """删除指定角色的所有会话"""
    char_chat_dir = chat_dir(character_id)
    if not char_chat_dir.exists():
        return
    for p in list_json_files(char_chat_dir):
        with _lock_for(p):
            p.unlink(missing_ok=True)
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
        for p in list_json_files(character_dir):
            try:
                chat = Chat.model_validate(read_json(p))
                if chat.isGroup:
                    out.append(chat)
            except Exception:
                continue
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


