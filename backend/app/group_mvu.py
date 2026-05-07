"""群聊 MVU：成员是否具备可感知 MVU 数据、会话是否启用 MVU 运行时、从角色快照写入会话。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas import CharacterCard, Chat, ChatOverrides, StateVariables, StatusTableDef

_EXTRACT_ACTIONS = frozenset({"extract", "extract_and_replace"})


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def character_has_mvu_profile_data(card: CharacterCard | Any) -> bool:
    """与前端 characterHasMvuProfileData 对齐：有初始表、有指令、或有提取类正文正则之一即视为具备 MVU 数据。"""
    tables = list(getattr(card, "initialStateTables", None) or [])
    if len(tables) > 0:
        return True
    d = getattr(card, "mvuDirective", None)
    if d is not None and str(d).strip():
        return True
    for r in list(getattr(card, "contentRegexRules", None) or []):
        if str(getattr(r, "action", "") or "").strip() in _EXTRACT_ACTIONS:
            return True
    return False


def is_chat_mvu_runtime_enabled(chat: Chat) -> bool:
    """单聊：沿用角色卡 mvuEnabled。群聊：显式 groupMvuEnabled；未设置时回退旧行为（首位成员的 mvuEnabled）。"""
    from app.storage import load_character

    if not getattr(chat, "isGroup", False):
        try:
            c = load_character(chat.characterId)
        except Exception:
            return False
        return bool(getattr(c, "mvuEnabled", False))
    ov = chat.overrides
    explicit = getattr(ov, "groupMvuEnabled", None)
    if explicit is True:
        return True
    if explicit is False:
        return False
    try:
        c = load_character(chat.characterId)
    except Exception:
        return False
    return bool(getattr(c, "mvuEnabled", False))


def maybe_migrate_legacy_group_mvu_on_save(chat: Chat) -> None:
    """旧群聊：首位成员曾开 MVU 且未写入显式字段时，懒迁移为锚定 ID。"""
    from app.storage import load_character

    if not getattr(chat, "isGroup", False):
        return
    ov = chat.overrides
    if getattr(ov, "groupMvuAnchorCharacterId", None):
        return
    if getattr(ov, "groupMvuEnabled", None) is not None:
        return
    try:
        c = load_character(chat.characterId)
    except Exception:
        return
    if not bool(getattr(c, "mvuEnabled", False)):
        return
    ov.groupMvuEnabled = True
    ov.groupMvuAnchorCharacterId = chat.characterId


def apply_character_mvu_snapshot_to_group_chat(chat: Chat, card: CharacterCard) -> None:
    """将角色 MVU 模式/指令/初始状态表写入群聊会话；不修改 contentRegexRules。"""
    mode = getattr(card, "mvuMode", None)
    chat.overrides.mvuMode = mode if mode in ("regex", "directive") else "regex"
    chat.overrides.mvuDirective = getattr(card, "mvuDirective", None)
    tables_raw = list(getattr(card, "initialStateTables", None) or [])
    if tables_raw:
        tables: list[StatusTableDef] = []
        for t in tables_raw:
            if isinstance(t, StatusTableDef):
                tables.append(t.model_copy(deep=True))
            else:
                tables.append(StatusTableDef.model_validate(t))
        chat.stateVariables = StateVariables(
            version=1,
            updatedAt=_now_iso(),
            source="chat_assistant",
            tables=tables,
        )
    else:
        chat.stateVariables = None
