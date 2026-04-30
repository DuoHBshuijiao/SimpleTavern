"""
数据存储操作模块

本模块提供所有数据存储相关的操作，包括：
- 文件路径管理（角色、聊天、头像、设置等）
- JSON文件的读写操作（带文件锁保护）
- 角色卡片的CRUD操作
- 聊天会话的CRUD操作
- 头像文件的保存和删除
- AI助手相关数据的存储
- 长期记忆的存储和管理

主要功能：
    - 路径管理：提供各种数据目录和文件路径的获取函数
    - 文件锁：使用portalocker实现文件锁，防止并发写入冲突
    - 数据持久化：所有数据以JSON格式存储在本地文件系统中
    - 数据初始化：确保必要的目录和默认文件存在

主要函数：
    - ensure_data_initialized: 初始化数据目录和默认文件
    - read_json/write_json: JSON文件读写（带锁）
    - load_settings/save_settings: 设置管理
    - list_characters/load_character/save_character/delete_character: 角色管理
    - list_chats/load_chat/save_chat/delete_chat: 聊天管理
    - save_avatar/delete_avatar: 头像管理
    - load_assistant_settings/save_assistant_settings: AI助手设置管理
    - load_assistant_chat/save_assistant_chat: AI助手聊天记录管理

文件关系：
    - 被导入：被main.py和所有routes模块导入
    - 导入：导入schemas.py中的模型类
    - 依赖：依赖schemas.py提供的数据模型
    - 位置：数据访问层，提供统一的数据存储接口
"""

from __future__ import annotations

import json
import os
import re
import shutil
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import portalocker

from datetime import datetime

from app.attachment_policy import normalize_mime_type
from app.schemas import AssistantAttachment, AssistantChat, AssistantSettings, Chat, ChatImageAttachment, ChatMessage, CharacterCard, MvuWorkLogEntry, Settings, StateVariables, WorldBook


def _repo_root() -> Path:
    """
    获取仓库根目录路径
    
    通过当前文件路径向上查找两级目录（backend/app/storage.py -> backend/app -> backend -> repoRoot）
    
    Returns:
        Path: 仓库根目录的Path对象
    """
    return Path(__file__).resolve().parents[2]


def _data_dir() -> Path:
    """
    获取数据目录路径
    
    Returns:
        Path: data目录的Path对象
    """
    return _repo_root() / "data"


def _characters_dir() -> Path:
    """
    获取角色目录路径
    
    Returns:
        Path: data/characters目录的Path对象
    """
    return _data_dir() / "characters"


def _chats_dir() -> Path:
    """
    获取聊天目录路径
    
    Returns:
        Path: data/chats目录的Path对象
    """
    return _data_dir() / "chats"


def _avatars_dir() -> Path:
    """
    获取头像目录路径
    
    Returns:
        Path: data/avatars目录的Path对象
    """
    return _data_dir() / "avatars"


def _ai_workspace_dir() -> Path:
    """
    获取AI工作空间目录路径
    
    Returns:
        Path: data/ai_workspace目录的Path对象
    """
    return _data_dir() / "ai_workspace"


def _assistant_ingest_dir() -> Path:
    return _ai_workspace_dir() / "ingest"


def _assistant_chat_ingest_root() -> Path:
    return _assistant_ingest_dir() / "assistant_chat"


def _workspace_session_ingest_root() -> Path:
    return _assistant_ingest_dir() / "workspace_session"


def _fonts_dir() -> Path:
    """
    获取字体目录路径
    
    Returns:
        Path: data/fonts目录的Path对象
    """
    return _data_dir() / "fonts"


def _page_backgrounds_dir() -> Path:
    """
    获取页面背景图目录路径

    Returns:
        Path: data/page_backgrounds 目录的Path对象
    """
    return _data_dir() / "page_backgrounds"


def _shader_presets_dir() -> Path:
    """
    获取 WebGPU 着色器预设目录路径

    Returns:
        Path: data/shader_presets 目录的Path对象
    """
    return _data_dir() / "shader_presets"


def _worldbooks_dir() -> Path:
    """
    获取世界书目录路径

    Returns:
        Path: data/worldbooks目录的Path对象
    """
    return _data_dir() / "worldbooks"


def _tts_cache_dir() -> Path:
    """TTS 合成音频缓存目录。"""
    return _data_dir() / "tts_cache"


def get_tts_cache_dir() -> Path:
    """返回 TTS 缓存目录，供路由/服务层使用。"""
    return _tts_cache_dir()


def get_huggingface_data_dir() -> Path:
    """
    Hugging Face 缓存根目录（用作子进程 HF_HOME）。

    Hub 快照与 model.safetensors 等通常位于 ``<此路径>/hub``。
    """
    return _data_dir() / "huggingface"


def apply_hf_cache_env(env: dict[str, str]) -> None:
    """
    将 HF / Transformers / PyTorch Hub 缓存定向到 data/huggingface 下。

    仅设置 ``HF_HOME``（不再设置已弃用的 ``TRANSFORMERS_CACHE``；Transformers 会跟随 HF_HOME）。
    仅影响传入的 env（例如托管 TTS 子进程），不修改当前进程的全局环境。
    """
    hf = get_huggingface_data_dir()
    env["HF_HOME"] = str(hf)
    env.pop("TRANSFORMERS_CACHE", None)
    env["TORCH_HOME"] = str(hf / "torch")


def get_repo_root() -> Path:
    """返回仓库根目录，供更新等模块使用。"""
    return _repo_root()


def get_update_dir() -> Path:
    """返回 data/update 目录，用于存放更新包。"""
    return _data_dir() / "update"


def update_ignore_path() -> Path:
    """返回 data/update_ignore.json 路径。"""
    return _data_dir() / "update_ignore.json"


def load_update_ignore() -> dict[str, Any]:
    """读取更新忽略配置；损坏时自愈为 {}。"""
    path = update_ignore_path()
    if not path.exists():
        return {}
    try:
        raw = read_json(path)
    except Exception:
        write_json(path, {})
        return {}
    return raw if isinstance(raw, dict) else {}


def save_update_ignore(ignored_release_tag: str | None) -> dict[str, str]:
    """保存 ignoredReleaseTag；空值会写入空对象。"""
    tag = (ignored_release_tag or "").strip()
    payload: dict[str, str] = {}
    if tag:
        payload["ignoredReleaseTag"] = tag
    write_json(update_ignore_path(), payload)
    return payload


def _settings_path() -> Path:
    """
    获取设置文件路径
    
    Returns:
        Path: data/settings.json的Path对象
    """
    return _data_dir() / "settings.json"


def _assistant_settings_path() -> Path:
    """
    获取AI助手设置文件路径
    
    Returns:
        Path: data/assistant_settings.json的Path对象
    """
    return _data_dir() / "assistant_settings.json"


def _assistant_chat_path() -> Path:
    """
    获取AI助手聊天记录文件路径
    
    Returns:
        Path: data/assistant_chat.json的Path对象
    """
    return _data_dir() / "assistant_chat.json"


def _assistant_workspace_chat_path() -> Path:
    """
    获取AI助手工作空间聊天记录文件路径
    
    Returns:
        Path: data/ai_workspace/assistant_workspace_chat.json的Path对象
    """
    return _ai_workspace_dir() / "assistant_workspace_chat.json"

CHAT_RECORD_FILENAME = "chat.json"
CHAT_MEMORY_FILENAME = "chat_memory.json"
ASSISTANT_CHAT_FILENAME = "assistant_chat.json"
ASSISTANT_WORKSPACE_CHAT_FILENAME = "assistant_workspace_chat.json"


def ensure_data_initialized() -> None:
    """
    确保数据目录和默认文件已初始化
    
    创建所有必要的数据目录（data、characters、chats、avatars、ai_workspace），
    如果默认配置文件不存在，则创建默认配置。
    """
    _data_dir().mkdir(parents=True, exist_ok=True)
    _characters_dir().mkdir(parents=True, exist_ok=True)
    _chats_dir().mkdir(parents=True, exist_ok=True)
    _avatars_dir().mkdir(parents=True, exist_ok=True)
    _fonts_dir().mkdir(parents=True, exist_ok=True)
    _page_backgrounds_dir().mkdir(parents=True, exist_ok=True)
    _shader_presets_dir().mkdir(parents=True, exist_ok=True)
    _ai_workspace_dir().mkdir(parents=True, exist_ok=True)
    _assistant_ingest_dir().mkdir(parents=True, exist_ok=True)
    _worldbooks_dir().mkdir(parents=True, exist_ok=True)
    _tts_cache_dir().mkdir(parents=True, exist_ok=True)
    get_huggingface_data_dir().mkdir(parents=True, exist_ok=True)

    if not _settings_path().exists():
        settings = Settings()
        write_json(_settings_path(), settings.model_dump(mode="json"))
    if not _assistant_settings_path().exists():
        settings = AssistantSettings()
        write_json(_assistant_settings_path(), settings.model_dump(mode="json"))
    if not _assistant_chat_path().exists():
        chat = AssistantChat()
        write_json(_assistant_chat_path(), chat.model_dump(mode="json"))


@dataclass(frozen=True)
class LockedFile:
    """
    文件锁上下文管理器
    
    用于管理文件锁的获取和释放，确保文件操作的线程安全。
    
    主要属性：
        lock_path: 锁文件路径
        lock_handle: 锁文件句柄
    """
    lock_path: Path
    lock_handle: Any

    def __enter__(self) -> "LockedFile":
        """
        进入上下文管理器
        
        Returns:
            LockedFile: 自身实例
        """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        退出上下文管理器，释放文件锁
        
        Args:
            exc_type: 异常类型
            exc: 异常实例
            tb: 追溯信息
        """
        try:
            portalocker.unlock(self.lock_handle)
        finally:
            self.lock_handle.close()


def _lock_for(target: Path) -> LockedFile:
    """
    为目标文件创建文件锁
    
    单用户应用也可能因前端并发请求导致短暂并发写，使用文件锁规避写入撕裂。
    
    Args:
        target: 需要加锁的目标文件路径
    
    Returns:
        LockedFile: 文件锁上下文管理器
    """
    lock_path = Path(str(target) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    portalocker.lock(fh, portalocker.LOCK_EX)
    return LockedFile(lock_path=lock_path, lock_handle=fh)


def read_json(path: Path) -> dict[str, Any]:
    """
    读取JSON文件（带文件锁保护）
    
    Args:
        path: JSON文件路径
    
    Returns:
        dict[str, Any]: 解析后的JSON数据
    
    Raises:
        FileNotFoundError: 文件不存在时抛出
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    with _lock_for(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    """
    写入JSON文件（带文件锁保护，使用临时文件确保原子性）
    
    先写入临时文件，然后原子性地替换原文件，确保写入过程的完整性。
    
    Args:
        path: JSON文件路径
        obj: 要写入的对象（会被序列化为JSON）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    with _lock_for(path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)


def list_json_files(dir_path: Path) -> list[Path]:
    """
    列出目录下所有JSON文件
    
    Args:
        dir_path: 目录路径
    
    Returns:
        list[Path]: JSON文件路径列表，按文件名排序
    """
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() == ".json"])


def load_settings() -> Settings:
    """
    加载全局设置
    
    Returns:
        Settings: 设置对象
    """
    raw = read_json(_settings_path())
    settings = Settings.model_validate(raw)
    needs_migration = isinstance(raw, dict) and "worldBookEntryScanDepthDefault" not in raw
    pruned = prune_webgpu_shader_presets(settings)
    if needs_migration or pruned:
        save_settings(settings)
    return settings


def save_settings(settings: Settings) -> Settings:
    """
    保存全局设置
    
    自动更新updatedAt时间戳。
    
    Args:
        settings: 设置对象
    
    Returns:
        Settings: 保存后的设置对象
    """
    prune_webgpu_shader_presets(settings)
    settings.updatedAt = datetime.now().astimezone().isoformat()
    if getattr(settings, "worldBookEntryScanDepthDefault", None) is None:
        settings.worldBookEntryScanDepthDefault = 2
    write_json(_settings_path(), settings.model_dump(mode="json"))
    return settings


def settings_path() -> Path:
    """
    获取设置文件路径（公开接口）
    
    Returns:
        Path: settings.json文件路径
    """
    return _settings_path()


def assistant_settings_path() -> Path:
    """
    获取AI助手设置文件路径（公开接口）
    
    Returns:
        Path: assistant_settings.json文件路径
    """
    return _assistant_settings_path()


def assistant_chat_path() -> Path:
    """
    获取AI助手聊天记录文件路径（公开接口）
    
    Returns:
        Path: assistant_chat.json文件路径
    """
    return _assistant_chat_path()


def assistant_workspace_chat_path() -> Path:
    """
    获取AI助手工作空间聊天记录文件路径（公开接口）
    
    Returns:
        Path: assistant_workspace_chat.json文件路径
    """
    return _assistant_workspace_chat_path()


def assistant_chat_path_for_chat(chat_id: str) -> Path:
    """
    获取指定聊天会话的AI助手聊天记录文件路径
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        Path: 该会话的assistant_chat.json文件路径
    
    Raises:
        FileNotFoundError: 聊天会话不存在时抛出
    """
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        raise FileNotFoundError(chat_id)
    _, character_id = found
    return chat_folder(character_id, chat_id) / ASSISTANT_CHAT_FILENAME


def characters_dir() -> Path:
    """
    获取角色目录路径（公开接口）
    
    Returns:
        Path: characters目录路径
    """
    return _characters_dir()


def chats_dir() -> Path:
    """
    获取聊天目录路径（公开接口）
    
    Returns:
        Path: chats目录路径
    """
    return _chats_dir()


def worldbooks_dir() -> Path:
    """
    获取世界书目录路径（公开接口）

    Returns:
        Path: worldbooks目录路径
    """
    return _worldbooks_dir()


def worldbook_path(worldbook_id: str) -> Path:
    """
    获取世界书文件路径

    Args:
        worldbook_id: 世界书ID

    Returns:
        Path: 世界书JSON文件路径
    """
    return _worldbooks_dir() / f"{worldbook_id}.json"


def ai_workspace_dir() -> Path:
    """
    获取AI工作空间目录路径（公开接口）
    
    Returns:
        Path: ai_workspace目录路径
    """
    return _ai_workspace_dir()


def assistant_ingest_dir() -> Path:
    """返回 data/ai_workspace/ingest 目录。"""
    return _assistant_ingest_dir()


def assistant_chat_ingest_dir(chat_id: str) -> Path:
    """返回聊天助手附件目录 data/ai_workspace/ingest/assistant_chat/{chat_id}。"""
    return _assistant_chat_ingest_root() / _normalize_attachment_storage_key(chat_id)


def workspace_session_ingest_dir(session_id: str) -> Path:
    """返回工作区临时附件目录 data/ai_workspace/ingest/workspace_session/{session_id}。"""
    return _workspace_session_ingest_root() / _normalize_attachment_storage_key(session_id)


def _normalize_attachment_storage_key(value: str) -> str:
    key = (value or "").strip()
    if not key or any(token in key for token in ("..", "/", "\\")):
        raise ValueError("invalid attachment storage key")
    return key


def _assistant_attachment_dir(storage_scope: str, storage_key: str) -> Path:
    if storage_scope == "assistant_chat":
        return assistant_chat_ingest_dir(storage_key)
    if storage_scope == "workspace_session":
        return workspace_session_ingest_dir(storage_key)
    raise ValueError("invalid attachment storage scope")


def _safe_attachment_ext(mime_type: str | None, original_name: str | None = None) -> str:
    original_suffix = Path(original_name or "").suffix.strip()
    if original_suffix:
        return original_suffix if original_suffix.startswith(".") else f".{original_suffix}"
    return _safe_image_ext_from_mime(mime_type)


def workspace_character_card_path() -> Path:
    """
    工作区角色卡草稿文件路径（与 GET /assistant/workspace/character-card 一致）

    Returns:
        Path: data/ai_workspace/character_card.json
    """
    return _ai_workspace_dir() / "character_card.json"


def save_workspace_character_card(card: CharacterCard) -> CharacterCard:
    """
    将角色卡暂存为工作区草稿（覆盖写入 character_card.json）

    Args:
        card: 角色卡片（经 Pydantic 校验）

    Returns:
        CharacterCard: 写入后的同一对象
    """
    path = workspace_character_card_path()
    write_json(path, card.model_dump(mode="json"))
    return card


def character_path(character_id: str) -> Path:
    """
    获取角色卡片文件路径
    
    Args:
        character_id: 角色ID
    
    Returns:
        Path: 角色JSON文件路径（{character_id}.json）
    """
    return _characters_dir() / f"{character_id}.json"


def list_characters() -> list[CharacterCard]:
    """
    列出所有角色卡片
    
    按更新时间倒序排列。如果某个文件损坏无法解析，会跳过该文件。
    
    Returns:
        list[CharacterCard]: 角色卡片列表，按updatedAt倒序
    """
    out: list[CharacterCard] = []
    for p in list_json_files(_characters_dir()):
        try:
            out.append(CharacterCard.model_validate(read_json(p)))
        except Exception:
            continue
    out.sort(key=lambda c: c.updatedAt, reverse=True)
    return out


def load_character(character_id: str) -> CharacterCard:
    """
    加载指定角色卡片
    
    Args:
        character_id: 角色ID
    
    Returns:
        CharacterCard: 角色卡片对象
    
    Raises:
        FileNotFoundError: 角色不存在时抛出
    """
    return CharacterCard.model_validate(read_json(character_path(character_id)))


def save_character(card: CharacterCard) -> CharacterCard:
    """
    保存角色卡片
    
    Args:
        card: 角色卡片对象
    
    Returns:
        CharacterCard: 保存后的角色卡片对象
    """
    write_json(character_path(card.id), card.model_dump(mode="json"))
    return card


def list_worldbooks() -> list[WorldBook]:
    """
    列出所有世界书

    Returns:
        list[WorldBook]: 世界书列表，按更新时间倒序
    """
    out: list[WorldBook] = []
    for p in list_json_files(_worldbooks_dir()):
        try:
            out.append(WorldBook.model_validate(read_json(p)))
        except Exception:
            continue
    out.sort(key=lambda w: w.updatedAt, reverse=True)
    return out


def load_worldbook(worldbook_id: str) -> WorldBook:
    """
    加载指定世界书
    """
    return WorldBook.model_validate(read_json(worldbook_path(worldbook_id)))


def save_worldbook(book: WorldBook) -> WorldBook:
    """
    保存世界书并维护互斥字段约束
    """
    now = datetime.now().astimezone().isoformat()
    if not getattr(book, "createdAt", None):
        book.createdAt = now
    book.updatedAt = now
    if bool(book.globalActive):
        book.sessionChatIds = []
    else:
        book.sessionChatIds = list(dict.fromkeys([cid for cid in (book.sessionChatIds or []) if cid]))
    data = book.model_dump(mode="json")
    for e in data.get("entries") or []:
        if isinstance(e, dict):
            e.pop("insertDepth", None)
            e.pop("scanDepth", None)
    write_json(worldbook_path(book.id), data)
    return book


def delete_worldbook(worldbook_id: str) -> None:
    """
    删除世界书文件及其锁文件（与 delete_chat 一致，避免残留 *.json.lock）
    """
    p = worldbook_path(worldbook_id)
    if p.exists():
        with _lock_for(p):
            p.unlink(missing_ok=True)
    _lock_file_path(p).unlink(missing_ok=True)


def delete_character(character_id: str, delete_related_chats: bool = True) -> None:
    """
    删除角色卡片
    
    可选择是否同时删除该角色关联的所有聊天会话。
    
    Args:
        character_id: 角色ID
        delete_related_chats: 是否同时删除关联的聊天会话，默认为True
    """
    p = character_path(character_id)
    if p.exists():
        with _lock_for(p):
            p.unlink(missing_ok=True)
    
    if delete_related_chats:
        delete_chats_by_character(character_id)


def chat_dir(character_id: str) -> Path:
    """
    获取角色的聊天目录路径
    
    Args:
        character_id: 角色ID
    
    Returns:
        Path: 该角色的聊天目录路径（data/chats/{character_id}）
    """
    return _chats_dir() / character_id


def chat_folder(character_id: str, chat_id: str) -> Path:
    """
    获取聊天会话文件夹路径
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    
    Returns:
        Path: 聊天会话文件夹路径（data/chats/{character_id}/{chat_id}）
    """
    return chat_dir(character_id) / chat_id


def chat_record_path(character_id: str, chat_id: str) -> Path:
    """
    获取聊天记录文件路径
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    
    Returns:
        Path: 聊天记录文件路径（data/chats/{character_id}/{chat_id}/chat.json）
    """
    return chat_folder(character_id, chat_id) / CHAT_RECORD_FILENAME


def chat_memory_path(character_id: str, chat_id: str) -> Path:
    """
    获取聊天长期记忆文件路径
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    
    Returns:
        Path: 长期记忆文件路径（data/chats/{character_id}/{chat_id}/chat_memory.json）
    """
    return chat_folder(character_id, chat_id) / CHAT_MEMORY_FILENAME


def _mvu_logs_path(character_id: str, chat_id: str) -> Path:
    """返回 MVU 工作日志文件路径（data/chats/{character_id}/{chat_id}/mvu_logs.json）。"""
    return chat_folder(character_id, chat_id) / "mvu_logs.json"


def chat_images_dir(character_id: str, chat_id: str) -> Path:
    """返回会话图片目录（data/chats/{character_id}/{chat_id}/images）。"""
    return chat_folder(character_id, chat_id) / "images"


def _safe_image_ext_from_mime(mime_type: str | None) -> str:
    if not mime_type:
        return ".png"
    guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip().lower())
    if guessed:
        return guessed
    return ".png"


def save_chat_image(
    *,
    chat: Chat,
    data: bytes,
    mime_type: str,
    original_name: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> ChatImageAttachment:
    """保存聊天图片并返回附件元数据。"""
    image_id = uuid4().hex
    ext = _safe_image_ext_from_mime(mime_type)
    filename = f"{image_id}{ext}"
    target = chat_images_dir(chat.characterId, chat.id) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return ChatImageAttachment(
        id=image_id,
        filename=filename,
        mimeType=mime_type,
        size=len(data),
        width=width,
        height=height,
        originalName=original_name,
    )


def save_assistant_attachment(
    *,
    data: bytes,
    kind: str,
    storage_scope: str,
    storage_key: str,
    mime_type: str,
    original_name: str | None = None,
) -> AssistantAttachment:
    """保存助手附件到 ai_workspace/ingest 子树并返回元数据。"""
    attachment_id = uuid4().hex
    ext = _safe_attachment_ext(mime_type, original_name)
    filename = f"{attachment_id}{ext}"
    target = _assistant_attachment_dir(storage_scope, storage_key) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return AssistantAttachment(
        id=attachment_id,
        kind=kind,
        storageScope=storage_scope,
        storageKey=_normalize_attachment_storage_key(storage_key),
        filename=filename,
        mimeType=normalize_mime_type(mime_type) or "application/octet-stream",
        size=len(data),
        originalName=original_name,
    )


def assistant_attachment_path(attachment: AssistantAttachment) -> Path:
    """返回助手附件完整路径。"""
    if Path(attachment.filename).name != attachment.filename:
        raise ValueError("invalid attachment filename")
    return _assistant_attachment_dir(attachment.storageScope, attachment.storageKey) / attachment.filename


def load_assistant_attachment_bytes(attachment: AssistantAttachment) -> bytes:
    """读取助手附件二进制。"""
    path = assistant_attachment_path(attachment)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_bytes()


def delete_assistant_attachment_file(attachment: AssistantAttachment) -> None:
    """删除单个助手附件文件。"""
    path = assistant_attachment_path(attachment)
    if path.exists():
        path.unlink(missing_ok=True)


def prune_assistant_chat_attachments(chat_id: str, messages: list[ChatMessage]) -> None:
    """按当前助手聊天消息引用清理聊天作用域下未被使用的附件文件。"""
    base = assistant_chat_ingest_dir(chat_id)
    if not base.exists():
        return
    keep: set[str] = set()
    for message in messages:
        for attachment in getattr(message, "attachments", []) or []:
            if getattr(attachment, "storageScope", None) != "assistant_chat":
                continue
            if getattr(attachment, "storageKey", None) != chat_id:
                continue
            filename = getattr(attachment, "filename", None)
            if filename:
                keep.add(filename)
    for path in base.iterdir():
        if not path.is_file():
            continue
        if path.name not in keep:
            path.unlink(missing_ok=True)
    if not any(base.iterdir()):
        base.rmdir()


def clear_assistant_chat_attachments(chat_id: str | None = None) -> None:
    """删除聊天助手 ingest 目录；chat_id 为空时清空整棵 assistant_chat 子树。"""
    target = _assistant_chat_ingest_root() if not chat_id else assistant_chat_ingest_dir(chat_id)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def clear_workspace_session_attachments(session_id: str) -> None:
    """删除指定 workspace_session 附件目录。"""
    target = workspace_session_ingest_dir(session_id)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def chat_image_path(character_id: str, chat_id: str, image_filename: str) -> Path:
    """返回聊天图片完整路径。"""
    return chat_images_dir(character_id, chat_id) / image_filename


def copy_chat_images_for_promote(
    source_character_id: str,
    source_chat_id: str,
    messages: list[ChatMessage],
    dest_character_id: str,
    dest_chat_id: str,
) -> None:
    """将消息中引用的图片从源会话目录复制到目标会话目录（不删除源文件）。"""
    seen: set[tuple[str, str]] = set()
    for msg in messages:
        for image in getattr(msg, "images", []) or []:
            fn = getattr(image, "filename", None) or ""
            if not fn:
                continue
            key = (source_chat_id, fn)
            if key in seen:
                continue
            seen.add(key)
            src = chat_image_path(source_character_id, source_chat_id, fn)
            if not src.is_file():
                continue
            dst = chat_image_path(dest_character_id, dest_chat_id, fn)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def load_chat_image_bytes(chat: Chat, image: ChatImageAttachment) -> bytes:
    """读取聊天图片二进制。"""
    path = chat_image_path(chat.characterId, chat.id, image.filename)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_bytes()


def delete_chat_image(chat: Chat, image: ChatImageAttachment) -> None:
    """删除聊天图片文件（若存在）。"""
    path = chat_image_path(chat.characterId, chat.id, image.filename)
    if path.exists():
        path.unlink(missing_ok=True)


def delete_message_images(chat: Chat, message: ChatMessage) -> None:
    """删除单条消息关联图片。"""
    for image in getattr(message, "images", []) or []:
        try:
            delete_chat_image(chat, image)
        except Exception:
            continue


def legacy_chat_path(character_id: str, chat_id: str) -> Path:
    """
    获取旧版聊天文件路径（兼容旧格式）
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    
    Returns:
        Path: 旧版聊天文件路径（data/chats/{character_id}/{chat_id}.json）
    """
    return chat_dir(character_id) / f"{chat_id}.json"


def _attach_chat_memory(chat: Chat) -> None:
    """
    将长期记忆附加到聊天对象的overrides中
    
    如果长期记忆文件存在，则加载并附加到chat.overrides.longTermMemory。
    
    Args:
        chat: 聊天对象（会被修改）
    """
    try:
        memory = load_chat_memory(chat.characterId, chat.id)
    except FileNotFoundError:
        memory = None
    if memory is not None:
        chat.overrides.longTermMemory = memory
    else:
        chat.overrides.longTermMemory = None


def _sanitize_chat_greeting_variants(chat: Chat) -> None:
    """移除 greetingVariants 中的空串；不足两条时去掉多版本元数据；校正 greetingVariantIndex 与 content 一致。"""
    for m in chat.messages:
        gv = getattr(m, "greetingVariants", None)
        if not gv:
            if getattr(m, "greetingVariantReasoningContents", None):
                m.greetingVariantReasoningContents = None
            continue
        cleaned = [str(x).strip() for x in gv if x is not None and str(x).strip()]
        if len(cleaned) >= 2:
            m.greetingVariants = cleaned
            gvr = getattr(m, "greetingVariantReasoningContents", None) or None
            if gvr and isinstance(gvr, list) and len(gvr) < len(cleaned):
                while len(gvr) < len(cleaned):
                    gvr.append("")
                m.greetingVariantReasoningContents = gvr[: len(cleaned)]
            elif gvr and isinstance(gvr, list) and len(gvr) > len(cleaned):
                m.greetingVariantReasoningContents = gvr[: len(cleaned)]
            cur = (m.content or "").strip()
            idx = getattr(m, "greetingVariantIndex", None)
            if isinstance(idx, int) and 0 <= idx < len(cleaned) and cleaned[idx] == cur:
                continue
            if cur in cleaned:
                m.greetingVariantIndex = cleaned.index(cur)
            else:
                m.content = cleaned[0]
                m.greetingVariantIndex = 0
            continue
        m.greetingVariants = None
        m.greetingVariantIndex = None
        if hasattr(m, "greetingVariantReasoningContents"):
            m.greetingVariantReasoningContents = None
        if len(cleaned) == 1:
            m.content = cleaned[0]


def _load_chat_from_path(path: Path, character_id: str) -> Chat | None:
    """
    从指定路径加载聊天对象
    
    如果加载失败或characterId不匹配，返回None。
    
    Args:
        path: 聊天文件路径
        character_id: 期望的角色ID
    
    Returns:
        Chat | None: 聊天对象，加载失败返回None
    """
    try:
        chat = Chat.model_validate(read_json(path))
    except Exception:
        return None
    if chat.characterId != character_id:
        chat.characterId = character_id
    _attach_chat_memory(chat)
    _sanitize_chat_greeting_variants(chat)
    return chat


def list_chats(character_id: str) -> list[Chat]:
    """
    列出指定角色的所有聊天会话
    
    支持新格式（文件夹+chat.json）和旧格式（{chat_id}.json），
    按更新时间倒序排列。
    
    Args:
        character_id: 角色ID
    
    Returns:
        list[Chat]: 聊天会话列表，按updatedAt倒序
    """
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
    """
    通过聊天ID查找聊天文件路径和角色ID
    
    无数据库设计，需要扫描所有角色目录以定位chatId。
    优先查找新格式（文件夹+chat.json），如果不存在则查找旧格式（{chat_id}.json）。
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        tuple[Path, str] | None: (聊天文件路径, 角色ID)元组，未找到返回None
    """
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
    """
    加载指定聊天会话
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        Chat: 聊天对象
    
    Raises:
        FileNotFoundError: 聊天不存在时抛出
    """
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        raise FileNotFoundError(chat_id)
    p, character_id = found
    chat = _load_chat_from_path(p, character_id)
    if chat is None:
        raise FileNotFoundError(chat_id)
    return chat


def mark_last_message_memory_updated(chat: Chat) -> None:
    """
    在长期记忆更新后，清除所有消息的 memoryUpdatedAfterThis，仅在最新一条消息的 extra 中写入 memoryUpdatedAfterThis = True。
    不执行保存，由调用方 save_chat。
    """
    if not chat.messages:
        return
    for i, msg in enumerate(chat.messages):
        d = msg.model_dump(mode="json")
        d.pop("memoryUpdatedAfterThis", None)
        chat.messages[i] = ChatMessage.model_validate(d)
    d = chat.messages[-1].model_dump(mode="json")
    d["memoryUpdatedAfterThis"] = True
    chat.messages[-1] = ChatMessage.model_validate(d)


def save_chat(chat: Chat) -> Chat:
    """
    保存聊天会话

    如果聊天对象中有长期记忆，会单独保存到chat_memory.json文件。
    同时会删除旧格式的聊天文件（如果存在）。

    Args:
        chat: 聊天对象

    Returns:
        Chat: 保存后的聊天对象
    """
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
    """
    加载聊天长期记忆
    
    支持两种格式：dict格式（longTermMemory或content字段）和纯字符串格式。
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    
    Returns:
        str | None: 长期记忆内容，不存在返回None
    
    Raises:
        FileNotFoundError: 长期记忆文件不存在时抛出
    """
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
    """
    保存聊天长期记忆
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
        content: 长期记忆内容
    """
    path = chat_memory_path(character_id, chat_id)
    write_json(path, {"longTermMemory": content})


_MVU_LOGS_MAX_ENTRIES = 200


def load_mvu_logs(character_id: str, chat_id: str) -> list[MvuWorkLogEntry]:
    """读取 MVU 工作日志。文件不存在时返回空列表。"""
    path = _mvu_logs_path(character_id, chat_id)
    if not path.exists():
        return []
    raw = read_json(path)
    if isinstance(raw, list):
        return [MvuWorkLogEntry.model_validate(item) for item in raw]
    return []


def save_mvu_logs(character_id: str, chat_id: str, entries: list[MvuWorkLogEntry]) -> None:
    """写入 MVU 工作日志，超过 200 条自动轮转保留最近条目。"""
    path = _mvu_logs_path(character_id, chat_id)
    kept = entries[-_MVU_LOGS_MAX_ENTRIES:] if len(entries) > _MVU_LOGS_MAX_ENTRIES else list(entries)
    write_json(path, [e.model_dump(mode="json") for e in kept])


def load_chat_state_variables(chat_id: str) -> StateVariables | None:
    """读取会话 stateVariables。"""
    chat = load_chat(chat_id)
    return chat.stateVariables


def save_chat_state_variables(chat_id: str, state: StateVariables) -> Chat:
    """原子写入 stateVariables，版本递增，更新时间戳。"""
    chat = load_chat(chat_id)
    state.version = (state.version or 0) + 1
    state.updatedAt = datetime.now().astimezone().isoformat()
    chat.stateVariables = state
    return save_chat(chat)


def _lock_file_path(target: Path) -> Path:
    """返回与目标文件对应的锁文件路径（与 _lock_for 中一致）。"""
    return Path(str(target) + ".lock")


def delete_chat_memory(character_id: str, chat_id: str) -> None:
    """
    删除聊天长期记忆
    
    删除 chat_memory.json 及其锁文件 chat_memory.json.lock。
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    """
    path = chat_memory_path(character_id, chat_id)
    if path.exists():
        with _lock_for(path):
            path.unlink(missing_ok=True)
    lock_path = _lock_file_path(path)
    lock_path.unlink(missing_ok=True)


def delete_chat(chat_id: str) -> None:
    """
    删除聊天会话
    
    删除聊天记录文件、长期记忆文件及其锁文件（如 chat.json.lock），
    并删除磁盘上的会话目录（data/chats/{character_id}/{chat_id}/）。
    
    Args:
        chat_id: 聊天会话ID
    """
    found = _find_chat_path_by_id(chat_id)
    if found is None:
        return
    p, character_id = found
    with _lock_for(p):
        p.unlink(missing_ok=True)
    _lock_file_path(p).unlink(missing_ok=True)
    delete_chat_memory(character_id, chat_id)
    chat_dir_path = chat_folder(character_id, chat_id)
    if chat_dir_path.exists():
        try:
            shutil.rmtree(chat_dir_path)
        except OSError:
            pass


def delete_chats_by_character(character_id: str) -> None:
    """
    删除指定角色的所有聊天会话
    
    递归删除该角色目录下的所有文件和文件夹。
    
    Args:
        character_id: 角色ID
    """
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
    try:
        char_chat_dir.rmdir()
    except OSError:
        pass


def list_group_chats() -> list[Chat]:
    """
    列出所有群聊会话
    
    扫描所有角色的聊天目录，筛选出isGroup=True的聊天会话。
    
    Returns:
        list[Chat]: 群聊会话列表，按updatedAt倒序
    """
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


def avatars_dir() -> Path:
    """
    获取头像目录路径（公开接口）
    
    Returns:
        Path: avatars目录路径
    """
    return _avatars_dir()


def avatar_path(filename: str) -> Path:
    """
    获取头像文件路径
    
    Args:
        filename: 头像文件名
    
    Returns:
        Path: 头像文件完整路径
    """
    return _avatars_dir() / filename


def save_avatar(filename: str, data: bytes) -> str:
    """
    保存头像文件
    
    Args:
        filename: 头像文件名
        data: 头像文件二进制数据
    
    Returns:
        str: 保存的文件名
    """
    p = avatar_path(filename)
    p.write_bytes(data)
    return filename


def delete_avatar(filename: str) -> None:
    """
    删除头像文件
    
    Args:
        filename: 头像文件名
    """
    if not filename:
        return
    p = avatar_path(filename)
    if p.exists():
        p.unlink(missing_ok=True)


def fonts_dir() -> Path:
    """
    获取字体目录路径（公开接口）

    Returns:
        Path: data/fonts 目录路径
    """
    return _fonts_dir()


def font_path(filename: str) -> Path:
    """
    获取字体文件路径

    Args:
        filename: 字体文件名

    Returns:
        Path: 字体文件完整路径
    """
    return _fonts_dir() / filename


def save_font(filename: str, data: bytes) -> str:
    """
    保存字体文件到 data/fonts，不随备份导出。

    Args:
        filename: 字体文件名（需为安全文件名）
        data: 字体文件二进制数据

    Returns:
        str: 保存的文件名
    """
    p = font_path(filename)
    p.write_bytes(data)
    return filename


def page_backgrounds_dir() -> Path:
    """
    获取页面背景图目录路径（公开接口）

    Returns:
        Path: data/page_backgrounds 目录路径
    """
    return _page_backgrounds_dir()


def page_background_path(filename: str) -> Path:
    """
    获取页面背景图文件路径

    Args:
        filename: 背景图文件名

    Returns:
        Path: 背景图文件完整路径
    """
    return _page_backgrounds_dir() / filename


def save_page_background(filename: str, data: bytes) -> str:
    """
    保存页面背景图到 data/page_backgrounds。

    Args:
        filename: 背景图文件名（需为安全文件名）
        data: 背景图二进制数据

    Returns:
        str: 保存的文件名
    """
    p = page_background_path(filename)
    p.write_bytes(data)
    return filename


def delete_page_background(filename: str) -> None:
    """
    删除页面背景图文件

    Args:
        filename: 背景图文件名
    """
    if not filename:
        return
    p = page_background_path(filename)
    if p.exists():
        p.unlink(missing_ok=True)


def shader_presets_dir() -> Path:
    """
    获取 WebGPU 着色器预设目录路径（公开接口）

    Returns:
        Path: data/shader_presets 目录路径
    """
    return _shader_presets_dir()


def shader_preset_path(filename: str) -> Path:
    """
    获取 WebGPU 着色器预设文件路径

    Args:
        filename: 着色器文件名

    Returns:
        Path: 着色器文件完整路径
    """
    return _shader_presets_dir() / filename


# 须与 frontend/src/utils/normalizeWgslSource.ts 行为一致
_WGSL_SPACE_LIKE_RE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")


def normalize_wgsl_source(source: str) -> str:
    """
    规范化 WGSL 源码：去 BOM、CRLF→LF、类空格 Unicode→ASCII 空格。
    """
    if source.startswith("\ufeff"):
        source = source[1:]
    source = source.replace("\r\n", "\n")
    source = _WGSL_SPACE_LIKE_RE.sub(" ", source)
    return source


def save_shader_preset(filename: str, source: str) -> str:
    """
    保存 WebGPU 着色器预设源码到 data/shader_presets。

    Args:
        filename: 着色器文件名（需为安全文件名）
        source: WGSL 源码

    Returns:
        str: 保存后的文件名
    """
    p = shader_preset_path(filename)
    p.write_text(normalize_wgsl_source(source), encoding="utf-8")
    return filename


def load_shader_preset(filename: str) -> str:
    """
    读取 WebGPU 着色器预设源码。

    Args:
        filename: 着色器文件名

    Returns:
        str: WGSL 源码
    """
    p = shader_preset_path(filename)
    return normalize_wgsl_source(p.read_text(encoding="utf-8"))


def delete_shader_preset(filename: str) -> None:
    """
    删除 WebGPU 着色器预设文件

    Args:
        filename: 着色器文件名
    """
    if not filename:
        return
    p = shader_preset_path(filename)
    if p.exists():
        p.unlink(missing_ok=True)


_WGSL_SHADER_PRESET_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def _is_safe_shader_preset_wgsl_filename(wgsl_file: str) -> bool:
    """与 shader_presets 路由一致：仅允许安全 basename 的 .wgsl 文件名。"""
    if not wgsl_file:
        return False
    p = Path(wgsl_file)
    if p.name != wgsl_file:
        return False
    if p.suffix.lower() != ".wgsl":
        return False
    return bool(_WGSL_SHADER_PRESET_FILENAME_RE.match(p.name))


def prune_webgpu_shader_presets(settings: Settings) -> bool:
    """
    移除指向缺失或非法 WGSL 文件的预设元数据；修正活动预设 ID。

    Returns:
        bool: 若 settings 被修改则 True
    """
    before = list(settings.webgpuBackgroundPresets)
    kept = []
    for p in before:
        if not _is_safe_shader_preset_wgsl_filename(p.wgslFile):
            continue
        if shader_preset_path(Path(p.wgslFile).name).exists():
            kept.append(p)
    changed = len(kept) != len(before)
    settings.webgpuBackgroundPresets = kept
    active = settings.webgpuBackgroundActivePresetId
    if active and not any(p.id == active for p in kept):
        settings.webgpuBackgroundActivePresetId = kept[0].id if kept else None
        changed = True
    return changed


def _assistant_chat_has_missing_ids(raw: Any) -> bool:
    """
    检查AI助手聊天记录中是否有消息缺少ID
    
    用于兼容旧数据格式，自动为缺少ID的消息生成ID。
    
    Args:
        raw: 原始JSON数据
    
    Returns:
        bool: 如果存在缺少ID的消息返回True，否则返回False
    """
    if not isinstance(raw, dict):
        return False
    messages = raw.get("messages")
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if isinstance(msg, dict) and not msg.get("id"):
            return True
    return False


def _assistant_raw_fix_missing_tool_call_ids(raw: Any) -> bool:
    """
    为 role=tool 但缺少 tool_call_id 的消息补全占位 id，避免 model_validate 失败。
    返回是否修改了 raw（用于与 missing id 修复一样写回磁盘）。
    """
    if not isinstance(raw, dict):
        return False
    messages = raw.get("messages")
    if not isinstance(messages, list):
        return False
    changed = False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        t = msg.get("tool_call_id")
        if t is None or (isinstance(t, str) and not t.strip()):
            msg["tool_call_id"] = f"legacy_missing_{uuid4().hex}"
            changed = True
    return changed


def load_assistant_settings() -> AssistantSettings:
    """
    加载AI助手设置
    
    Returns:
        AssistantSettings: AI助手设置对象
    """
    raw = read_json(_assistant_settings_path())
    return AssistantSettings.model_validate(raw)


def save_assistant_settings(settings: AssistantSettings) -> AssistantSettings:
    """
    保存AI助手设置
    
    Args:
        settings: AI助手设置对象
    
    Returns:
        AssistantSettings: 保存后的设置对象
    """
    write_json(_assistant_settings_path(), settings.model_dump(mode="json"))
    return settings


def load_assistant_chat() -> AssistantChat:
    """
    加载AI助手聊天记录（全局）
    
    如果发现消息缺少ID，会自动修复并保存。
    
    Returns:
        AssistantChat: AI助手聊天对象
    """
    path = _assistant_chat_path()
    raw = read_json(path)
    fixed_tool_ids = _assistant_raw_fix_missing_tool_call_ids(raw)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw) or fixed_tool_ids:
        write_json(path, chat.model_dump(mode="json"))
    return chat


def load_assistant_workspace_chat() -> AssistantChat:
    """
    加载AI助手工作空间聊天记录
    
    如果文件不存在，会创建新的空聊天记录。
    如果发现消息缺少ID，会自动修复并保存。
    
    Returns:
        AssistantChat: AI助手聊天对象
    """
    path = _assistant_workspace_chat_path()
    if not path.exists():
        chat = AssistantChat()
        write_json(path, chat.model_dump(mode="json"))
        return chat
    raw = read_json(path)
    fixed_tool_ids = _assistant_raw_fix_missing_tool_call_ids(raw)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw) or fixed_tool_ids:
        write_json(path, chat.model_dump(mode="json"))
    return chat


def load_assistant_chat_for_chat(chat_id: str) -> AssistantChat:
    """
    加载指定聊天会话的AI助手聊天记录
    
    如果文件不存在，会创建新的空聊天记录。
    如果发现消息缺少ID，会自动修复并保存。
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        AssistantChat: AI助手聊天对象
    
    Raises:
        FileNotFoundError: 聊天会话不存在时抛出
    """
    path = assistant_chat_path_for_chat(chat_id)
    if not path.exists():
        chat = AssistantChat()
        write_json(path, chat.model_dump(mode="json"))
        return chat
    raw = read_json(path)
    fixed_tool_ids = _assistant_raw_fix_missing_tool_call_ids(raw)
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw) or fixed_tool_ids:
        write_json(path, chat.model_dump(mode="json"))
    return chat


def save_assistant_chat(chat: AssistantChat) -> AssistantChat:
    """
    保存AI助手聊天记录（全局）
    
    Args:
        chat: AI助手聊天对象
    
    Returns:
        AssistantChat: 保存后的聊天对象
    """
    write_json(_assistant_chat_path(), chat.model_dump(mode="json"))
    return chat


def save_assistant_workspace_chat(chat: AssistantChat) -> AssistantChat:
    """
    保存AI助手工作空间聊天记录
    
    Args:
        chat: AI助手聊天对象
    
    Returns:
        AssistantChat: 保存后的聊天对象
    """
    write_json(_assistant_workspace_chat_path(), chat.model_dump(mode="json"))
    return chat


def save_assistant_chat_for_chat(chat_id: str, chat: AssistantChat) -> AssistantChat:
    """
    保存指定聊天会话的AI助手聊天记录
    
    Args:
        chat_id: 聊天会话ID
        chat: AI助手聊天对象
    
    Returns:
        AssistantChat: 保存后的聊天对象
    
    Raises:
        FileNotFoundError: 聊天会话不存在时抛出
    """
    path = assistant_chat_path_for_chat(chat_id)
    write_json(path, chat.model_dump(mode="json"))
    prune_assistant_chat_attachments(chat_id, chat.messages)
    return chat


def clear_assistant_chat() -> None:
    """
    清空AI助手聊天记录（全局）
    
    重置为空的聊天记录。
    """
    chat = AssistantChat()
    write_json(_assistant_chat_path(), chat.model_dump(mode="json"))
    clear_assistant_chat_attachments()


def clear_assistant_workspace_chat() -> None:
    """
    清空AI助手工作空间聊天记录
    
    重置为空的聊天记录。
    """
    chat = AssistantChat()
    write_json(_assistant_workspace_chat_path(), chat.model_dump(mode="json"))


def delete_assistant_workspace_chat() -> None:
    """
    删除AI助手工作空间聊天记录文件
    
    完全删除文件，而不是重置为空。
    """
    path = _assistant_workspace_chat_path()
    if path.exists():
        with _lock_for(path):
            path.unlink(missing_ok=True)


def clear_assistant_chat_for_chat(chat_id: str) -> None:
    """
    清空指定聊天会话的AI助手聊天记录
    
    Args:
        chat_id: 聊天会话ID
    
    Raises:
        FileNotFoundError: 聊天会话不存在时抛出
    """
    chat = AssistantChat()
    path = assistant_chat_path_for_chat(chat_id)
    write_json(path, chat.model_dump(mode="json"))
    clear_assistant_chat_attachments(chat_id)


def clear_ai_workspace() -> None:
    """
    清空AI工作空间
    
    递归删除ai_workspace目录下的所有文件和文件夹。
    """
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
