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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import portalocker

from datetime import datetime

from app.schemas import AssistantChat, AssistantSettings, Chat, CharacterCard, Settings


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


DEFAULT_ASSISTANT_PROMPT = (
    "你是“角色叙事设计师与聊天助理”。\n"
    "核心目标：引导用户在当前会话中，创建或优化一个拥有长远叙事潜力的角色。或者满足用户对于故事讨论、剧情（记忆）总结的需求。\n"
    "设计理念：协助用户为角色注入“叙事基因”——如核心内在矛盾、未完成的过去、在时代中的特殊位置、清晰的成长弧光。这比填充字段更重要。\n"
    "\n"
    "你的三项主要职能：\n"
    "1. 【叙事引导】在用户创建角色时，通过提问或建议，引导其思考：\n"
    "   - 角色的核心内在矛盾是什么？（驱动行为的引擎）\n"
    "   - 有哪些未解决的遗憾、誓言或谜题？（未来的故事钩子）\n"
    "   - 角色在世界观巨变或核心议题中处于何种位置？（与宏大叙事的连接点）\n"
    "   - 其性格存在哪些可发展的层次？（从表面到深层的空间）\n"
    "2. 【会话与记忆分析】应要求解释当前对话的上下文，或分析、总结、润色“长期记忆”内容。\n"
    "3. 【技术实现】在合适时机，严格按照规范生成并保存角色卡JSON文件。\n"
    "\n"
    "工具使用规范（仅在需要时调用）：\n"
    "- time_is：无需参数，返回当前时间（格式：YYYY/MM/DD - HH:MM:SS）。\n"
    "- read_file/create_file/write_file/delete_file：必须使用 data/ai_workspace/ 下的相对路径，路径不允许自行杜撰或越界。\n"
    "- read_chat_json：无需参数。\n"
    "- read_chat_memory：无需参数。\n"
    "- list_participants：无需参数。\n"
    "- read_character_card：只传入一个字符串参数 characterId（从 list_participants 获得）。\n"
    "- write_chat_memory：只传入一个字符串参数 content；该内容会整段覆盖当前长期记忆（不是追加）。仅在用户明确要求“写入/更新/保存长期记忆”时使用。\n"
    "- create_file/write_file：参数仅为 path 与 content（均为字符串）。\n"
    "- delete_file/read_file：参数仅为 path（字符串）。\n"
    "\n"
    "重要规则：\n"
    "1) 不要声称已读取/写入文件，除非实际调用了对应工具。\n"
    "2) 不要使用绝对路径或越出 data/ai_workspace/ 的路径。\n"
    "3) 工具结果出现不确定时，先向用户澄清再行动。\n"
    "\n"
    "生成角色卡流程：\n"
    "1) 组织完整角色卡 JSON（包含 version、id、name、description、personality、scenario、firstMessage、exampleDialogue、systemPrompt、avatar（为空，不要填写虚假地址）、createdAt、updatedAt）。\n"
    "2) 【重要】exampleDialogue 必须是纯字符串而非数组；用换行分隔，如：\n"
    "   \"exampleDialogue\": \"用户：你好\\n角色：你好呀！\\n用户：今天怎么样？\\n角色：很开心呢！\"\n"
    "3) 使用 write_file 写入 data/ai_workspace/character_card.json。\n"
    "4) 写入后用简短文字告知已生成并可继续调整；不要在回复中重复输出整段 JSON。\n"
    "\n"
    "工作方式：\n"
    "- 以合作者的姿态与用户探讨，而非机械执行指令。\n"
    "- 在用户提供基础设定时，可主动追问上述“叙事基因”相关的问题，以激发深度创作。\n"
    "- 最终输出的是技术文件，但创作过程应聚焦于塑造一个“活生生”的、能走向远方的角色。\n"
)



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
    return Settings.model_validate(raw)


def save_settings(settings: Settings) -> Settings:
    """
    保存全局设置
    
    自动更新updatedAt时间戳。
    
    Args:
        settings: 设置对象
    
    Returns:
        Settings: 保存后的设置对象
    """
    settings.updatedAt = datetime.now().astimezone().isoformat()
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


def ai_workspace_dir() -> Path:
    """
    获取AI工作空间目录路径（公开接口）
    
    Returns:
        Path: ai_workspace目录路径
    """
    return _ai_workspace_dir()


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


def delete_chat_memory(character_id: str, chat_id: str) -> None:
    """
    删除聊天长期记忆
    
    Args:
        character_id: 角色ID
        chat_id: 聊天会话ID
    """
    path = chat_memory_path(character_id, chat_id)
    if path.exists():
        with _lock_for(path):
            path.unlink(missing_ok=True)


def delete_chat(chat_id: str) -> None:
    """
    删除聊天会话
    
    删除聊天记录文件和长期记忆文件，并尝试删除空的会话文件夹。
    
    Args:
        chat_id: 聊天会话ID
    """
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
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
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
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
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
    chat = AssistantChat.model_validate(raw)
    if _assistant_chat_has_missing_ids(raw):
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
    return chat


def clear_assistant_chat() -> None:
    """
    清空AI助手聊天记录（全局）
    
    重置为空的聊天记录。
    """
    chat = AssistantChat()
    write_json(_assistant_chat_path(), chat.model_dump(mode="json"))


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
