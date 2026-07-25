"""群聊 MVU：成员是否具备可感知 MVU 数据、会话是否启用 MVU 运行时、从角色快照写入会话。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.errors import AppError
from app.schemas import CharacterCard, Chat, ChatOverrides, StateVariables, StatusTableDef

_EXTRACT_ACTIONS = frozenset({"extract", "extract_and_replace"})


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


@dataclass(frozen=True)
class MvuRuntimeEnablement:
    """MVU 运行时启用判定：区分「未开启」与「角色不可读」。"""

    enabled: bool
    character_error: AppError | None = None


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


def _character_unreadable_error(character_id: str, exc: BaseException) -> AppError:
    return AppError(
        code="mvu_character_unreadable",
        message="无法读取会话绑定角色，MVU 运行时不可用",
        detail=f"characterId={character_id}: {type(exc).__name__}: {exc}",
        source="mvu.runtime.enable",
        status_code=500,
        suggested_action="检查角色文件是否存在或已损坏，修复后重试",
    )


def resolve_chat_mvu_runtime_enablement(chat: Chat) -> MvuRuntimeEnablement:
    """单聊：沿用角色卡 mvuEnabled。群聊：显式 groupMvuEnabled；未设置时回退首位成员 mvuEnabled。"""
    from app.storage import load_character

    if not getattr(chat, "isGroup", False):
        try:
            c = load_character(chat.characterId)
        except Exception as exc:
            return MvuRuntimeEnablement(
                enabled=False,
                character_error=_character_unreadable_error(chat.characterId, exc),
            )
        return MvuRuntimeEnablement(enabled=bool(getattr(c, "mvuEnabled", False)))

    ov = chat.overrides
    explicit = getattr(ov, "groupMvuEnabled", None)
    if explicit is True:
        try:
            load_character(chat.characterId)
        except Exception as exc:
            return MvuRuntimeEnablement(
                enabled=False,
                character_error=_character_unreadable_error(chat.characterId, exc),
            )
        return MvuRuntimeEnablement(enabled=True)
    if explicit is False:
        return MvuRuntimeEnablement(enabled=False)
    try:
        c = load_character(chat.characterId)
    except Exception as exc:
        return MvuRuntimeEnablement(
            enabled=False,
            character_error=_character_unreadable_error(chat.characterId, exc),
        )
    return MvuRuntimeEnablement(enabled=bool(getattr(c, "mvuEnabled", False)))


def is_chat_mvu_runtime_enabled(chat: Chat) -> bool:
    """兼容布尔门控。角色不可读时返回 False；需要区分错误时请用 resolve_chat_mvu_runtime_enablement。"""
    return resolve_chat_mvu_runtime_enablement(chat).enabled


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
    except Exception as exc:
        # 迁移是 best-effort；角色不可读时跳过，不改写会话。
        _ = exc
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
