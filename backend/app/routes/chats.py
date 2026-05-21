"""
聊天管理路由模块

提供聊天会话的CRUD操作和消息管理API端点，支持单聊和群聊两种模式。

主要功能：
    - GET /chats: 获取指定角色的所有聊天会话
    - GET /chats/groups: 获取所有群聊会话
    - POST /chats: 创建新聊天会话（支持单聊和群聊）
    - GET /chats/{chat_id}: 获取指定聊天会话
    - PUT /chats/{chat_id}: 更新聊天会话信息
    - DELETE /chats/{chat_id}: 删除聊天会话
    - POST /chats/{chat_id}/messages: 追加消息
    - PUT /chats/{chat_id}/messages/{message_id}: 更新消息
    - DELETE /chats/{chat_id}/messages/{message_id}: 删除消息
    - POST /chats/{chat_id}/members/{member_id}: 添加群成员
    - DELETE /chats/{chat_id}/members/{member_id}: 移除群成员

主要函数：
    - get_chats: 获取指定角色的聊天列表
    - get_group_chats: 获取所有群聊
    - create_chat: 创建聊天会话
    - get_chat: 获取聊天会话
    - update_chat: 更新聊天会话
    - append_message: 追加消息
    - update_message: 更新消息
    - delete_message: 删除消息
    - remove_chat: 删除聊天会话
    - add_member: 添加群成员
    - remove_member: 移除群成员

文件关系：
    - 被导入：被main.py导入router
    - 导入：导入schemas.py的聊天相关模型和storage.py的聊天管理函数
    - 依赖：依赖schemas.py和storage.py
    - 位置：路由层，处理聊天相关的HTTP请求
"""

from __future__ import annotations

import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.attachment_policy import ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES, is_image_mime_type
from app.content_regex_scanner import ensure_content_regex_scanner_started
from app.placeholders import replace_placeholders_in_text
from app.group_mvu import (
    apply_character_mvu_snapshot_to_group_chat,
    character_has_mvu_profile_data,
)
from app.schemas import (
    AppendMessageRequest,
    Chat,
    ChatContentRegexRule,
    ChatImageAttachment,
    ChatMessage,
    ChatOverrides,
    CreateChatRequest,
    ForkChatRequest,
    ForkLineageResponse,
    ForkOrigin,
    ForkOutgoingGroup,
    ForkSiblingSummary,
    PromoteToGroupRequest,
    StateVariables,
    UpdateChatRequest,
    UpdateMessageRequest,
    WorldBookAttachment,
)
from app.storage import (
    chat_image_path,
    copy_chat_images_for_promote,
    delete_chat,
    delete_chat_image,
    delete_message_images,
    iter_fork_chat_summaries,
    list_chats,
    list_group_chats,
    load_character,
    load_chat,
    load_settings,
    mark_last_message_memory_updated,
    save_chat,
    save_chat_image,
)

router = APIRouter(tags=["chats"])
ensure_content_regex_scanner_started()


def _now_iso() -> str:
    """
    获取当前时间的ISO格式字符串
    
    Returns:
        str: 当前时间的ISO格式字符串
    """
    return datetime.now().astimezone().isoformat()


def _clear_greeting_multivariant_on_other_assistants(chat: Chat, keep_message_id: str) -> None:
    """同一会话中仅保留一条 assistant 的多版本元数据，清除其他条上遗留的变体信息。"""
    for msg in chat.messages:
        if msg.id == keep_message_id or msg.role != "assistant":
            continue
        if getattr(msg, "greetingVariants", None) is None and getattr(
            msg, "greetingVariantIndex", None
        ) is None and getattr(msg, "greetingVariantReasoningContents", None) is None:
            continue
        msg.greetingVariants = None
        msg.greetingVariantIndex = None
        if hasattr(msg, "greetingVariantReasoningContents"):
            msg.greetingVariantReasoningContents = None
        if hasattr(msg, "greetingVariantReasoningDurations"):
            msg.greetingVariantReasoningDurations = None


def _apply_greeting_variants_on_update(
    m: ChatMessage, req: UpdateMessageRequest, req_dump: dict, chat: Chat
) -> None:
    if "greetingVariants" not in req_dump:
        return
    raw = req.greetingVariants
    if raw is None or (isinstance(raw, list) and len(raw) == 0):
        m.greetingVariants = None
        m.greetingVariantIndex = None
        if hasattr(m, "greetingVariantReasoningContents"):
            m.greetingVariantReasoningContents = None
        if hasattr(m, "greetingVariantReasoningDurations"):
            m.greetingVariantReasoningDurations = None
        return

    raw_texts = [str(x).strip() if x is not None else "" for x in raw]
    reasoning_src = req.greetingVariantReasoningContents if (
        "greetingVariantReasoningContents" in req_dump and req.greetingVariantReasoningContents is not None
    ) else None
    if reasoning_src is not None:
        kept_indices = [
            i
            for i, text in enumerate(raw_texts)
            if text or (i < len(reasoning_src) and str(reasoning_src[i] or "").strip())
        ]
    else:
        kept_indices = [i for i, text in enumerate(raw_texts) if text]
    cleaned = [raw_texts[i] for i in kept_indices]
    if len(cleaned) >= 2:
        m.greetingVariants = cleaned
        idx: int
        gvi = req.greetingVariantIndex
        if "greetingVariantIndex" in req_dump and isinstance(gvi, int) and 0 <= gvi < len(cleaned):
            idx = gvi
        else:
            cur = (m.content or "").strip()
            idx = cleaned.index(cur) if cur in cleaned else 0
        m.greetingVariantIndex = idx
        m.content = cleaned[idx]

        if "greetingVariantReasoningContents" in req_dump and req.greetingVariantReasoningContents is not None:
            raw_src = [str(x) if x is not None else "" for x in req.greetingVariantReasoningContents]
            src = [raw_src[i] if i < len(raw_src) else "" for i in kept_indices]
            while len(src) < len(cleaned):
                src.append("")
            m.greetingVariantReasoningContents = src[: len(cleaned)]
            r_one = m.greetingVariantReasoningContents[idx].strip() if 0 <= idx < len(
                m.greetingVariantReasoningContents
            ) else ""
            m.reasoningContent = r_one if r_one else None
        else:
            m.greetingVariantReasoningContents = None

        if "greetingVariantReasoningDurations" in req_dump and req.greetingVariantReasoningDurations is not None:
            raw_dur_src = [
                float(x) if x is not None and float(x) > 0 else None
                for x in req.greetingVariantReasoningDurations
            ]
            dur_src = [raw_dur_src[i] if i < len(raw_dur_src) else None for i in kept_indices]
            while len(dur_src) < len(cleaned):
                dur_src.append(None)
            m.greetingVariantReasoningDurations = dur_src[: len(cleaned)]
            d_one = m.greetingVariantReasoningDurations[idx] if 0 <= idx < len(m.greetingVariantReasoningDurations) else None
            m.reasoningDurationSec = d_one
        else:
            m.greetingVariantReasoningDurations = None

        _clear_greeting_multivariant_on_other_assistants(chat, m.id)
    elif len(cleaned) == 1:
        m.greetingVariants = None
        m.greetingVariantIndex = None
        m.greetingVariantReasoningContents = None
        m.greetingVariantReasoningDurations = None
        m.content = cleaned[0]
    else:
        m.greetingVariants = None
        m.greetingVariantIndex = None
        m.greetingVariantReasoningContents = None
        m.greetingVariantReasoningDurations = None


def _single_chat_greeting_variants(character, user_name: str) -> list[str]:
    """
    单聊开场候选：主首句（非空）在前，其后为 extraFirstMessageEntries 中非空 text，均已替换占位符。
    占位符替换后若为空字符串则丢弃，避免出现无法切换的空变体。
    """
    char_name = character.name or "角色"
    un = user_name or "用户"
    variants: list[str] = []

    def _push_replaced(raw: str) -> None:
        s = replace_placeholders_in_text(raw, char_name=char_name, user_name=un)
        s = (s or "").strip()
        if s:
            variants.append(s)

    fm = (character.firstMessage or "").strip()
    if fm:
        _push_replaced(fm)
    for entry in character.extraFirstMessageEntries or []:
        if not getattr(entry, "chip", True):
            continue
        raw = (entry.text or "").strip()
        if raw:
            _push_replaced(raw)
    return variants


def _copy_content_regex_rules(rules: list[ChatContentRegexRule] | None) -> list[ChatContentRegexRule]:
    out: list[ChatContentRegexRule] = []
    for rule in rules or []:
        try:
            data = rule.model_dump(mode="json")
        except Exception:
            continue
        out.append(ChatContentRegexRule.model_validate(data))
    return out


def _merge_group_regex_rules_via_mvu(member_rules: list[tuple[str, list[ChatContentRegexRule]]]) -> list[ChatContentRegexRule]:
    """群聊规则归并入口（当前以确定性去重实现，后续可替换为第三Agent任务）。"""
    merged: list[ChatContentRegexRule] = []
    seen: set[tuple[str, str, str]] = set()
    order = 0
    for _, rules in member_rules:
        for rule in rules:
            key = (
                (rule.pattern or "").strip(),
                (rule.action or "remove").strip(),
                (rule.replacement or "").strip(),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            r = ChatContentRegexRule.model_validate(rule.model_dump(mode="json"))
            r.order = order
            order += 1
            merged.append(r)
    return merged


def _rebuild_group_content_regex_from_members(chat: Chat) -> None:
    """按成员合并会话级正文正则（与新建群聊一致）。"""
    member_rules: list[tuple[str, list[ChatContentRegexRule]]] = []
    any_mvu_enabled = False
    for mid in chat.memberIds:
        try:
            card = load_character(mid)
            rules = _copy_content_regex_rules(getattr(card, "contentRegexRules", None) or [])
            member_rules.append((mid, rules))
            if bool(getattr(card, "mvuEnabled", False)):
                any_mvu_enabled = True
        except FileNotFoundError:
            continue
    if any_mvu_enabled:
        chat.overrides.contentRegexRules = _merge_group_regex_rules_via_mvu(member_rules)
    else:
        flat: list[ChatContentRegexRule] = []
        for _, rules in member_rules:
            flat.extend(rules)
        chat.overrides.contentRegexRules = _merge_group_regex_rules_via_mvu([("fallback", flat)])


def _apply_group_mvu_create_preset(chat: Chat, req: CreateChatRequest) -> None:
    """群聊创建：根据请求应用 MVU 预设（不修改已合并的 contentRegexRules）。"""
    preset = req.groupMvuPreset or "off"
    if preset == "off":
        chat.overrides.groupMvuEnabled = False
        return
    pid = (req.groupMvuPresetCharacterId or "").strip()
    if not pid or pid not in chat.memberIds:
        raise HTTPException(status_code=400, detail="groupMvuPresetCharacterId must be a group member")
    try:
        card = load_character(pid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="groupMvuPresetCharacterId character not found") from None
    if preset == "inherit_member" and not character_has_mvu_profile_data(card):
        raise HTTPException(
            status_code=400,
            detail="所选成员不具备可用的 MVU 配置数据（初始状态栏、MVU 指令或提取类正文正则）",
        )
    apply_character_mvu_snapshot_to_group_chat(chat, card)
    chat.overrides.groupMvuEnabled = True
    chat.overrides.groupMvuAnchorCharacterId = pid
    chat.overrides.groupMvuTemplateCharacterId = pid


def _validate_group_mvu_overrides(chat: Chat) -> None:
    if not chat.isGroup:
        return
    aid = getattr(chat.overrides, "groupMvuAnchorCharacterId", None)
    if aid and aid not in chat.memberIds:
        raise HTTPException(status_code=400, detail="groupMvuAnchorCharacterId must be in memberIds")
    tid = getattr(chat.overrides, "groupMvuTemplateCharacterId", None)
    if tid and tid not in chat.memberIds:
        raise HTTPException(status_code=400, detail="groupMvuTemplateCharacterId must be in memberIds")


def _merge_overrides(existing: Chat, incoming: UpdateChatRequest) -> None:
    """
    合并聊天覆盖设置
    
    将更新请求中的overrides合并到现有聊天对象中。
    对于params字段，只覆盖非None的值，避免一次更新清空所有旧参数。
    
    Args:
        existing: 现有的聊天对象（会被修改）
        incoming: 更新请求对象
    """
    if incoming.overrides is None:
        return
    ov = incoming.overrides
    if ov.prompt is not None:
        existing.overrides.prompt = ov.prompt
    if "sessionSystemPromptMode" in ov.model_fields_set:
        existing.overrides.sessionSystemPromptMode = ov.sessionSystemPromptMode
    if getattr(ov, "longTermMemory", None) is not None:
        existing.overrides.longTermMemory = ov.longTermMemory
    if hasattr(ov, "contextStartMessageId"):
        existing.overrides.contextStartMessageId = ov.contextStartMessageId
    if "contextStartKeepBeforeMessages" in ov.model_fields_set:
        existing.overrides.contextStartKeepBeforeMessages = ov.contextStartKeepBeforeMessages
    if getattr(ov, "pureAiMode", None) is not None:
        existing.overrides.pureAiMode = ov.pureAiMode
    if hasattr(ov, "presetId"):
        existing.overrides.presetId = ov.presetId
    if "worldBookAttachments" in ov.model_fields_set:
        existing.overrides.worldBookAttachments = list(ov.worldBookAttachments)
        existing.overrides.worldBookIds = [a.worldBookId for a in ov.worldBookAttachments]
    elif "worldBookIds" in ov.model_fields_set:
        wids = list(dict.fromkeys(getattr(ov, "worldBookIds", []) or []))
        existing.overrides.worldBookIds = wids
        existing.overrides.worldBookAttachments = [
            WorldBookAttachment(worldBookId=wid, scanDepth=None, insertDepth=5)
            for wid in wids
        ]
    if "worldBookGlobalExclusions" in ov.model_fields_set:
        existing.overrides.worldBookGlobalExclusions = list(
            dict.fromkeys(getattr(ov, "worldBookGlobalExclusions", []) or []),
        )
    if "contentRegexScanDepthDefault" in ov.model_fields_set:
        existing.overrides.contentRegexScanDepthDefault = max(1, int(ov.contentRegexScanDepthDefault or 1))
    if "contentRegexRules" in ov.model_fields_set:
        existing.overrides.contentRegexRules = _copy_content_regex_rules(getattr(ov, "contentRegexRules", []) or [])
    if "contentRegexEnabledByRuleId" in ov.model_fields_set:
        existing.overrides.contentRegexEnabledByRuleId = {
            str(k): bool(v) for k, v in (getattr(ov, "contentRegexEnabledByRuleId", {}) or {}).items()
        }
    if hasattr(ov, "draftHelp"):
        if existing.overrides.draftHelp is None:
            existing.overrides.draftHelp = ov.draftHelp
        elif hasattr(ov.draftHelp, "context_message_limit"):
            existing.overrides.draftHelp.context_message_limit = ov.draftHelp.context_message_limit
    if "tts" in ov.model_fields_set:
        existing.overrides.tts = ov.tts.model_copy(deep=True) if ov.tts is not None else None

    if "autoMemorySummaryEveryN" in ov.model_fields_set:
        existing.overrides.autoMemorySummaryEveryN = ov.autoMemorySummaryEveryN
    if "lastAutoMemorySummaryAfterMessageId" in ov.model_fields_set:
        existing.overrides.lastAutoMemorySummaryAfterMessageId = ov.lastAutoMemorySummaryAfterMessageId
    if "autoMemorySummarySilent" in ov.model_fields_set:
        existing.overrides.autoMemorySummarySilent = ov.autoMemorySummarySilent
    if "autoMemorySummaryNextAskTier" in ov.model_fields_set:
        existing.overrides.autoMemorySummaryNextAskTier = ov.autoMemorySummaryNextAskTier
    if "mvuMode" in ov.model_fields_set:
        existing.overrides.mvuMode = ov.mvuMode
    if "mvuDirective" in ov.model_fields_set:
        existing.overrides.mvuDirective = ov.mvuDirective
    if "groupMvuEnabled" in ov.model_fields_set:
        existing.overrides.groupMvuEnabled = ov.groupMvuEnabled
    if "groupMvuAnchorCharacterId" in ov.model_fields_set:
        existing.overrides.groupMvuAnchorCharacterId = ov.groupMvuAnchorCharacterId
    if "groupMvuTemplateCharacterId" in ov.model_fields_set:
        existing.overrides.groupMvuTemplateCharacterId = ov.groupMvuTemplateCharacterId
    if "knowledgeGraphEnabled" in ov.model_fields_set:
        existing.overrides.knowledgeGraphEnabled = ov.knowledgeGraphEnabled
    if "knowledgeGraphInjectPosition" in ov.model_fields_set:
        existing.overrides.knowledgeGraphInjectPosition = ov.knowledgeGraphInjectPosition
    if "knowledgeGraphInjectDepth" in ov.model_fields_set:
        existing.overrides.knowledgeGraphInjectDepth = max(0, int(ov.knowledgeGraphInjectDepth or 0))
    if "knowledgeGraphBeforeLastRole" in ov.model_fields_set:
        existing.overrides.knowledgeGraphBeforeLastRole = ov.knowledgeGraphBeforeLastRole

    for key in ("model", "temperature", "top_p", "max_tokens", "context_size"):
        val = getattr(ov.params, key, None)
        # context_size 允许显式设为 None 表示“未启用”；其他参数仅在有值时覆盖
        if key == "context_size" or val is not None:
            setattr(existing.overrides.params, key, val)


class UploadChatImageItem(BaseModel):
    imageData: str
    mimeType: str = "image/png"
    originalName: str | None = None
    width: int | None = None
    height: int | None = None


class UploadChatImagesRequest(BaseModel):
    images: list[UploadChatImageItem] = Field(default_factory=list)


class UploadChatImagesResponse(BaseModel):
    images: list[ChatImageAttachment] = Field(default_factory=list)


class ChatSearchHit(BaseModel):
    messageId: str
    messageIndex: int
    snippet: str


class ChatSearchResponse(BaseModel):
    query: str
    total: int
    hits: list[ChatSearchHit] = Field(default_factory=list)


@router.get("/chats", response_model=list[Chat])
def get_chats(characterId: str = Query(...)) -> list[Chat]:
    """
    获取指定角色的所有聊天会话
    
    Args:
        characterId: 角色ID（查询参数）
    
    Returns:
        list[Chat]: 聊天会话列表，按更新时间倒序
    """
    return list_chats(characterId)


@router.get("/chats/groups", response_model=list[Chat])
def get_group_chats() -> list[Chat]:
    """
    获取所有群聊会话
    
    Returns:
        list[Chat]: 群聊会话列表，按更新时间倒序
    """
    return list_group_chats()


@router.post("/chats", response_model=Chat)
def create_chat(req: CreateChatRequest) -> Chat:
    """
    创建新聊天会话
    
    支持单聊和群聊两种模式。对于单聊，如果角色有首条消息，会自动添加为assistant的第一条消息。
    对于群聊，可以选择启用某个成员的首条消息作为开场。
    会自动处理用户Persona的绑定和{{user}}占位符的替换。
    
    Args:
        req: 创建聊天请求对象
    
    Returns:
        Chat: 创建后的聊天对象
    
    Raises:
        HTTPException: 群聊时firstMessageCharacterId不是成员或角色不存在时抛出400或404错误
    """
    is_group = req.isGroup
    
    if is_group:
        title = req.title or "新群聊"
        member_ids = req.memberIds or []
        if req.characterId and req.characterId not in member_ids:
            member_ids = [req.characterId] + member_ids
        chat = Chat(
            characterId=req.characterId,
            title=title,
            isGroup=True,
            memberIds=member_ids
        )
    else:
        chat = Chat(characterId=req.characterId, title=req.title or "新对话")
    
    chat.overrides.pureAiMode = req.pureAiMode
    
    if is_group and req.memberSettings:
        for member_id, s in req.memberSettings.items():
            chat.memberSettings[member_id] = s
    if is_group:
        if req.groupSystemInjectDepth is not None:
            chat.groupSystemInjectDepth = int(req.groupSystemInjectDepth)
        if req.groupSystemAlwaysAtBottom is not None:
            chat.groupSystemAlwaysAtBottom = bool(req.groupSystemAlwaysAtBottom)

    chat.createdAt = _now_iso()
    chat.updatedAt = _now_iso()
    
    user_name = ""
    pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else False
    try:
        settings = load_settings()
        pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else bool(getattr(settings, "pureAiMode", False))
        if pure_ai_mode:
            user_name = "用户"
        else:
            persona_id = req.userPersonaId or settings.selectedPersonaId
            selected_persona = None
            if persona_id and settings.userPersonas:
                selected_persona = next((p for p in settings.userPersonas if p.id == persona_id), None)
            if selected_persona:
                user_name = selected_persona.name
        if not user_name:
            user_name = "用户"
    except Exception:
        pass

    if pure_ai_mode:
        chat.userPersonaId = None
    else:
        chat.userPersonaId = req.userPersonaId or (settings.selectedPersonaId if "settings" in locals() else None)
    
    if not is_group:
        try:
            character = load_character(req.characterId)
            chat.overrides.contentRegexRules = _copy_content_regex_rules(getattr(character, "contentRegexRules", None) or [])
            chat.overrides.mvuMode = getattr(character, "mvuMode", "regex")
            chat.overrides.mvuDirective = getattr(character, "mvuDirective", None)

            # 从角色卡初始状态栏定义写入会话 stateVariables
            initial_tables = list(getattr(character, "initialStateTables", None) or [])
            if initial_tables:
                chat.stateVariables = StateVariables(
                    version=1,
                    updatedAt=_now_iso(),
                    source="chat_assistant",
                    tables=initial_tables,
                )

            variants = _single_chat_greeting_variants(character, user_name or "用户")
            if len(variants) == 1:
                chat.messages.append(
                    ChatMessage(
                        role="assistant",
                        content=variants[0],
                    ),
                )
            elif len(variants) >= 2:
                chat.messages.append(
                    ChatMessage(
                        role="assistant",
                        content=variants[0],
                        greetingVariants=list(variants),
                        greetingVariantIndex=0,
                    ),
                )
        except FileNotFoundError:
            pass
    else:
        _rebuild_group_content_regex_from_members(chat)
        if req.firstMessageCharacterId:
            if req.firstMessageCharacterId not in chat.memberIds:
                raise HTTPException(status_code=400, detail="firstMessageCharacterId is not a member of this group")
            try:
                first_char = load_character(req.firstMessageCharacterId)
                if first_char.firstMessage and first_char.firstMessage.strip():
                    first_msg = first_char.firstMessage.strip()
                    first_msg = replace_placeholders_in_text(
                        first_msg,
                        char_name=(first_char.name or "角色"),
                        user_name=user_name or "用户",
                    )
                    chat.messages.append(ChatMessage(
                        role="assistant",
                        content=first_msg,
                        characterId=req.firstMessageCharacterId
                    ))
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="firstMessageCharacter not found")
        _apply_group_mvu_create_preset(chat, req)
        # 群聊创建：手工 MVU 草稿覆盖预设来源（在 _apply_group_mvu_create_preset 之后执行，
        # 用户在弹窗里直接编辑的模式 / 指令 / 正则 / 状态栏优先生效）
        if "mvuMode" in req.model_fields_set and req.mvuMode is not None:
            chat.overrides.mvuMode = req.mvuMode
        if "mvuDirective" in req.model_fields_set:
            chat.overrides.mvuDirective = req.mvuDirective or None
        if "contentRegexRules" in req.model_fields_set and req.contentRegexRules is not None:
            chat.overrides.contentRegexRules = _copy_content_regex_rules(req.contentRegexRules)
        if "initialStateTables" in req.model_fields_set and req.initialStateTables is not None:
            chat.stateVariables = StateVariables(
                version=1,
                updatedAt=_now_iso(),
                source="chat_assistant",
                tables=list(req.initialStateTables),
            )

    return save_chat(chat)


@router.post("/chats/{source_chat_id}/promote-to-group", response_model=Chat)
def promote_to_group(source_chat_id: str, req: PromoteToGroupRequest) -> Chat:
    """
    将单聊复制为新群聊：复制消息与图片，补全 assistant 的 characterId；不修改、不删除源单聊。
    """
    try:
        source = load_chat(source_chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found") from None

    if source.isGroup:
        raise HTTPException(status_code=400, detail="source is not a single chat")

    member_ids = list(req.memberIds)
    if len(member_ids) < 2:
        raise HTTPException(status_code=400, detail="memberIds must contain at least 2 members")
    if member_ids[0] != source.characterId:
        raise HTTPException(
            status_code=400,
            detail="memberIds[0] must equal the single chat's characterId",
        )
    if source.characterId not in member_ids:
        raise HTTPException(status_code=400, detail="memberIds must include the original character")

    for mid in member_ids:
        try:
            load_character(mid)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"character not found: {mid}") from None

    pure_ai_mode = req.pureAiMode if req.pureAiMode is not None else False
    try:
        settings = load_settings()
        if req.pureAiMode is None:
            pure_ai_mode = bool(getattr(settings, "pureAiMode", False))
    except Exception:
        settings = None  # type: ignore[assignment]

    title = (req.title or "").strip() or source.title or "新群聊"
    new_chat = Chat(
        characterId=member_ids[0],
        title=title,
        isGroup=True,
        memberIds=member_ids,
    )
    new_chat.overrides = source.overrides.model_copy(deep=True)
    new_chat.overrides.pureAiMode = pure_ai_mode

    if req.memberSettings:
        for member_id, s in req.memberSettings.items():
            new_chat.memberSettings[member_id] = s
    if req.groupSystemInjectDepth is not None:
        new_chat.groupSystemInjectDepth = int(req.groupSystemInjectDepth)
    if req.groupSystemAlwaysAtBottom is not None:
        new_chat.groupSystemAlwaysAtBottom = bool(req.groupSystemAlwaysAtBottom)

    if pure_ai_mode:
        new_chat.userPersonaId = None
    else:
        persona_id = req.userPersonaId
        if persona_id is None and settings is not None:
            persona_id = settings.selectedPersonaId
        new_chat.userPersonaId = persona_id

    new_chat.createdAt = _now_iso()
    new_chat.updatedAt = _now_iso()

    migrated: list[ChatMessage] = []
    for m in source.messages:
        d = m.model_dump(mode="json")
        if m.role == "assistant":
            d["characterId"] = m.characterId or source.characterId
        migrated.append(ChatMessage.model_validate(d))

    new_chat.messages = migrated

    _rebuild_group_content_regex_from_members(new_chat)
    new_chat.overrides.groupMvuEnabled = True
    new_chat.overrides.groupMvuAnchorCharacterId = source.characterId
    new_chat.overrides.groupMvuTemplateCharacterId = source.characterId
    if source.stateVariables is not None:
        new_chat.stateVariables = source.stateVariables.model_copy(deep=True)

    try:
        save_chat(new_chat)
        copy_chat_images_for_promote(
            source.characterId,
            source.id,
            new_chat.messages,
            new_chat.characterId,
            new_chat.id,
        )
    except Exception:
        try:
            delete_chat(new_chat.id)
        except Exception:
            pass
        raise

    return new_chat


@router.post("/chats/{source_chat_id}/branch", response_model=Chat)
def branch_chat(source_chat_id: str) -> Chat:
    """
    将单聊或群聊复制为新会话（种类不变）：复制消息与图片；
    标题在原名后追加「-新分支」；不复制 assistant_chat.json。
    """
    try:
        source = load_chat(source_chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found") from None

    base_title = (source.title or "").strip()
    if not base_title:
        base_title = "新群聊" if source.isGroup else "新对话"
    br_title = f"{base_title}-新分支"

    migrated: list[ChatMessage] = []
    cid = source.characterId
    for m in source.messages:
        d = m.model_dump(mode="json")
        if m.role == "assistant":
            d["characterId"] = m.characterId or cid
        migrated.append(ChatMessage.model_validate(d))

    if source.isGroup:
        member_ids = list(source.memberIds)
        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="group chat has fewer than 2 members")
        for mid in member_ids:
            try:
                load_character(mid)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"character not found: {mid}") from None

        new_chat = Chat(
            characterId=cid,
            title=br_title,
            isGroup=True,
            memberIds=list(member_ids),
        )
        new_chat.overrides = source.overrides.model_copy(deep=True)
        new_chat.userPersonaId = source.userPersonaId
        new_chat.groupDelay = source.groupDelay
        new_chat.groupSystemInjectDepth = source.groupSystemInjectDepth
        new_chat.groupSystemAlwaysAtBottom = source.groupSystemAlwaysAtBottom
        for mid, s in source.memberSettings.items():
            new_chat.memberSettings[mid] = s.model_copy(deep=True)
        if source.stateVariables is not None:
            new_chat.stateVariables = source.stateVariables.model_copy(deep=True)
    else:
        new_chat = Chat(
            characterId=cid,
            title=br_title,
            isGroup=False,
        )
        new_chat.overrides = source.overrides.model_copy(deep=True)
        new_chat.userPersonaId = source.userPersonaId
        if source.stateVariables is not None:
            new_chat.stateVariables = source.stateVariables.model_copy(deep=True)

    new_chat.createdAt = _now_iso()
    new_chat.updatedAt = _now_iso()
    new_chat.messages = migrated

    try:
        save_chat(new_chat)
        copy_chat_images_for_promote(
            source.characterId,
            source.id,
            new_chat.messages,
            new_chat.characterId,
            new_chat.id,
        )
    except Exception:
        try:
            delete_chat(new_chat.id)
        except Exception:
            pass
        raise

    return new_chat


def _message_index_1based(messages: list[ChatMessage], message_id: str) -> int | None:
    for i, m in enumerate(messages):
        if m.id == message_id:
            return i + 1
    return None


def _clear_fork_memory_overrides(overrides: ChatOverrides) -> None:
    """分叉新会话：时间线独立，清空长期记忆与上下文锚点。"""
    overrides.longTermMemory = None
    overrides.contextStartMessageId = None
    overrides.contextStartKeepBeforeMessages = None
    overrides.lastAutoMemorySummaryAfterMessageId = None


def _default_fork_title(source: Chat, custom: str | None) -> str:
    name = (custom or "").strip()
    if name:
        return name
    base = (source.title or "").strip()
    if not base:
        base = "新群聊" if source.isGroup else "新对话"
    return f"分叉：{base}"


def _fork_chat(source: Chat, fork_at_message_id: str, new_chat_name: str | None) -> Chat:
    fork_idx: int | None = None
    for i, m in enumerate(source.messages):
        if m.id == fork_at_message_id:
            fork_idx = i
            break
    if fork_idx is None:
        raise HTTPException(status_code=404, detail="message not found")

    fork_title = _default_fork_title(source, new_chat_name)
    cid = source.characterId
    migrated: list[ChatMessage] = []
    for m in source.messages[: fork_idx + 1]:
        d = m.model_dump(mode="json")
        if m.role == "assistant":
            d["characterId"] = m.characterId or cid
        migrated.append(ChatMessage.model_validate(d))

    if source.isGroup:
        member_ids = list(source.memberIds)
        if len(member_ids) < 2:
            raise HTTPException(status_code=400, detail="group chat has fewer than 2 members")
        for mid in member_ids:
            try:
                load_character(mid)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"character not found: {mid}") from None

        new_chat = Chat(
            characterId=cid,
            title=fork_title,
            isGroup=True,
            memberIds=list(member_ids),
        )
        new_chat.overrides = source.overrides.model_copy(deep=True)
        _clear_fork_memory_overrides(new_chat.overrides)
        new_chat.userPersonaId = source.userPersonaId
        new_chat.groupDelay = source.groupDelay
        new_chat.groupSystemInjectDepth = source.groupSystemInjectDepth
        new_chat.groupSystemAlwaysAtBottom = source.groupSystemAlwaysAtBottom
        for mid, s in source.memberSettings.items():
            new_chat.memberSettings[mid] = s.model_copy(deep=True)
    else:
        new_chat = Chat(
            characterId=cid,
            title=fork_title,
            isGroup=False,
        )
        new_chat.overrides = source.overrides.model_copy(deep=True)
        _clear_fork_memory_overrides(new_chat.overrides)
        new_chat.userPersonaId = source.userPersonaId

    new_chat.createdAt = _now_iso()
    new_chat.updatedAt = _now_iso()
    new_chat.messages = migrated
    new_chat.forkedFromChatId = source.id
    new_chat.forkedFromMessageId = fork_at_message_id
    new_chat.stateVariables = None

    try:
        save_chat(new_chat)
        copy_chat_images_for_promote(
            source.characterId,
            source.id,
            new_chat.messages,
            new_chat.characterId,
            new_chat.id,
        )
    except Exception:
        try:
            delete_chat(new_chat.id)
        except Exception:
            pass
        raise

    return new_chat


@router.post("/chats/{source_chat_id}/fork", response_model=Chat)
def fork_chat(source_chat_id: str, req: ForkChatRequest) -> Chat:
    """
    从指定消息（含）截断复制历史到新会话；不复制 stateVariables 与 assistant_chat.json。
    """
    try:
        source = load_chat(source_chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found") from None

    fork_at = (req.forkAtMessageId or "").strip()
    if not fork_at:
        raise HTTPException(status_code=400, detail="forkAtMessageId is required")

    return _fork_chat(source, fork_at, req.newChatName)


@router.get("/chats/{chat_id}/fork-lineage", response_model=ForkLineageResponse)
def get_fork_lineage(chat_id: str) -> ForkLineageResponse:
    """分叉溯源：来源、兄弟分叉、从本会话拉出的子分叉。"""
    try:
        current = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found") from None

    origin: ForkOrigin | None = None
    siblings: list[ForkSiblingSummary] = []
    src_chat_id = getattr(current, "forkedFromChatId", None)
    src_msg_id = getattr(current, "forkedFromMessageId", None)
    if src_chat_id and src_msg_id:
        try:
            src_chat = load_chat(src_chat_id)
        except FileNotFoundError:
            src_chat = None
        idx = (
            _message_index_1based(src_chat.messages, src_msg_id)
            if src_chat is not None
            else None
        )
        origin = ForkOrigin(
            chatId=src_chat_id,
            title=(src_chat.title if src_chat else "已删除的会话"),
            messageId=src_msg_id,
            messageIndex=idx if idx is not None else 1,
        )

    outgoing_by_msg: dict[str, list[ForkSiblingSummary]] = {}
    for summary in iter_fork_chat_summaries():
        if summary.id == chat_id:
            continue
        if summary.forkedFromChatId == chat_id and summary.forkedFromMessageId:
            mid = summary.forkedFromMessageId
            outgoing_by_msg.setdefault(mid, []).append(
                ForkSiblingSummary(
                    chatId=summary.id,
                    title=summary.title,
                    createdAt=summary.createdAt,
                )
            )
        if (
            src_chat_id
            and src_msg_id
            and summary.forkedFromChatId == src_chat_id
            and summary.forkedFromMessageId == src_msg_id
            and summary.id != chat_id
        ):
            siblings.append(
                ForkSiblingSummary(
                    chatId=summary.id,
                    title=summary.title,
                    createdAt=summary.createdAt,
                )
            )

    outgoing_forks: list[ForkOutgoingGroup] = []
    for mid, chats in outgoing_by_msg.items():
        idx = _message_index_1based(current.messages, mid)
        if idx is None:
            continue
        sorted_chats = sorted(chats, key=lambda c: c.createdAt, reverse=True)
        outgoing_forks.append(
            ForkOutgoingGroup(
                messageId=mid,
                messageIndex=idx,
                count=len(sorted_chats),
                chats=sorted_chats,
            )
        )
    outgoing_forks.sort(key=lambda g: g.messageIndex)

    siblings.sort(key=lambda c: c.createdAt, reverse=True)

    return ForkLineageResponse(
        origin=origin,
        siblings=siblings,
        outgoingForks=outgoing_forks,
    )


@router.get("/chats/{chat_id}", response_model=Chat)
def get_chat(chat_id: str) -> Chat:
    """
    获取指定聊天会话
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        Chat: 聊天对象
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")


@router.get("/chats/{chat_id}/search", response_model=ChatSearchResponse)
def search_chat(chat_id: str, q: str = Query(..., min_length=1)) -> ChatSearchResponse:
    """在当前会话正文中全文检索。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    query = q.strip()
    if not query:
        return ChatSearchResponse(query=q, total=0, hits=[])
    query_lower = query.lower()
    hits: list[ChatSearchHit] = []
    for idx, msg in enumerate(chat.messages):
        content = (msg.content or "").strip()
        if not content:
            continue
        pos = content.lower().find(query_lower)
        if pos < 0:
            continue
        start = max(0, pos - 32)
        end = min(len(content), pos + len(query) + 64)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        hits.append(ChatSearchHit(
            messageId=msg.id,
            messageIndex=idx,
            snippet=snippet,
        ))
        if len(hits) >= 300:
            break
    return ChatSearchResponse(query=query, total=len(hits), hits=hits)


@router.put("/chats/{chat_id}", response_model=Chat)
def update_chat(chat_id: str, req: UpdateChatRequest) -> Chat:
    """
    更新聊天会话
    
    支持更新标题、群聊延迟、成员列表（仅重排）、成员设置、用户Persona和覆盖设置。
    对于群聊的memberIds更新，仅允许重排（成员集合必须一致）。
    
    Args:
        chat_id: 聊天会话ID
        req: 更新请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在、非群聊尝试更新memberIds或成员集合不一致时抛出错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    if req.title is not None:
        chat.title = req.title
    if req.groupDelay is not None:
        chat.groupDelay = req.groupDelay
    if "groupSystemInjectDepth" in req.model_fields_set and req.groupSystemInjectDepth is not None:
        chat.groupSystemInjectDepth = max(0, int(req.groupSystemInjectDepth))
    if "groupSystemAlwaysAtBottom" in req.model_fields_set and req.groupSystemAlwaysAtBottom is not None:
        chat.groupSystemAlwaysAtBottom = bool(req.groupSystemAlwaysAtBottom)
    if req.memberIds is not None:
        if not chat.isGroup:
            raise HTTPException(status_code=400, detail="memberIds can only be updated for group chats")
        if set(req.memberIds) != set(chat.memberIds):
            raise HTTPException(status_code=400, detail="memberIds must contain the same members (reorder only)")
        chat.memberIds = req.memberIds
    if req.memberSettings is not None:
        for member_id, settings in req.memberSettings.items():
            chat.memberSettings[member_id] = settings
    if "userPersonaId" in req.model_fields_set:
        chat.userPersonaId = req.userPersonaId
    # 仅在本次请求真正修改了长期记忆内容时才标记 memoryUpdatedAfterThis，避免仅切换模型等操作时误触发
    incoming_memory = getattr(req.overrides, "longTermMemory", None) if req.overrides else None
    current_memory = getattr(chat.overrides, "longTermMemory", None) or ""
    memory_actually_changed = (
        incoming_memory is not None
        and (incoming_memory or "") != (current_memory or "")
    )
    _merge_overrides(chat, req)
    _validate_group_mvu_overrides(chat)
    if "stateVariables" in req.model_fields_set:
        if req.stateVariables is None:
            chat.stateVariables = None
        else:
            chat.stateVariables = req.stateVariables.model_copy(deep=True)
    if memory_actually_changed:
        mark_last_message_memory_updated(chat)
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.post("/chats/{chat_id}/messages", response_model=Chat)
def append_message(chat_id: str, req: AppendMessageRequest) -> Chat:
    """
    向聊天会话追加消息
    
    Args:
        chat_id: 聊天会话ID
        req: 追加消息请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    # 用户（或纯 AI 模式下首条 system）开始发言后，锁定开场白，去掉多版本元数据
    if req.role in ("user", "system"):
        for m in chat.messages:
            if m.role != "assistant":
                continue
            if not (
                getattr(m, "greetingVariants", None)
                or getattr(m, "greetingVariantIndex", None) is not None
                or getattr(m, "greetingVariantReasoningContents", None)
                or getattr(m, "greetingVariantReasoningDurations", None)
            ):
                continue
            m.greetingVariants = None
            m.greetingVariantIndex = None
            if hasattr(m, "greetingVariantReasoningContents"):
                m.greetingVariantReasoningContents = None
            if hasattr(m, "greetingVariantReasoningDurations"):
                m.greetingVariantReasoningDurations = None

    chat.messages.append(ChatMessage(
        role=req.role,
        content=req.content,
        images=getattr(req, "images", []) or [],
        characterId=req.characterId,
        senderPersonaId=getattr(req, "senderPersonaId", None),
        senderName=getattr(req, "senderName", None),
        senderAvatar=getattr(req, "senderAvatar", None),
        reasoningContent=req.reasoningContent,
        reasoningDurationSec=req.reasoningDurationSec,
    ))
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.put("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def update_message(chat_id: str, message_id: str, req: UpdateMessageRequest) -> Chat:
    """
    更新聊天会话中的消息
    
    支持更新消息的角色、内容、角色ID和发送者快照信息。
    发送者快照用于在切换Persona时保持历史消息的显示一致性。
    
    Args:
        chat_id: 聊天会话ID
        message_id: 消息ID
        req: 更新消息请求对象
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天或消息不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    for m in chat.messages:
        if m.id == message_id:
            old_images = list(getattr(m, "images", []) or [])
            stored_content = m.content
            m.role = req.role
            m.content = req.content
            if getattr(req, "images", None) is not None:
                m.images = req.images or []
                old_ids = {img.id for img in old_images}
                new_ids = {img.id for img in (m.images or [])}
                for old_img in old_images:
                    if old_img.id not in new_ids:
                        delete_chat_image(chat, old_img)
            # 仅当客户端显式传入 characterId 时更新，避免群聊中编辑仅改内容时覆盖发言人
            if req.characterId is not None:
                m.characterId = req.characterId
            if getattr(req, "senderPersonaId", None) is not None:
                m.senderPersonaId = req.senderPersonaId
            if getattr(req, "senderName", None) is not None:
                m.senderName = req.senderName
            if getattr(req, "senderAvatar", None) is not None:
                m.senderAvatar = req.senderAvatar
            req_dump = req.model_dump(exclude_unset=True)
            if "greetingVariants" in req_dump:
                _apply_greeting_variants_on_update(m, req, req_dump, chat)
            elif "greetingVariantIndex" in req_dump:
                m.greetingVariantIndex = req_dump["greetingVariantIndex"]
                gv = getattr(m, "greetingVariants", None)
                if (
                    isinstance(gv, list)
                    and len(gv) >= 2
                    and isinstance(m.greetingVariantIndex, int)
                    and 0 <= m.greetingVariantIndex < len(gv)
                ):
                    m.content = gv[m.greetingVariantIndex]
                    gvr = getattr(m, "greetingVariantReasoningContents", None)
                    if gvr and isinstance(gvr, list) and 0 <= m.greetingVariantIndex < len(gvr):
                        r0 = (gvr[m.greetingVariantIndex] or "").strip()
                        m.reasoningContent = r0 if r0 else None
            if "reasoningContent" in req_dump:
                m.reasoningContent = req_dump["reasoningContent"]
            if "reasoningDurationSec" in req_dump:
                m.reasoningDurationSec = req_dump["reasoningDurationSec"]
            if m.content != stored_content:
                m.ttsAudioAssetId = None
                m.ttsAudioSourceText = None
            chat.updatedAt = _now_iso()
            return save_chat(chat)

    raise HTTPException(status_code=404, detail="message not found")


@router.delete("/chats/{chat_id}/messages/{message_id}", response_model=Chat)
def delete_message(chat_id: str, message_id: str) -> Chat:
    """
    删除聊天会话中的消息
    
    Args:
        chat_id: 聊天会话ID
        message_id: 消息ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天或消息不存在时抛出404错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    before = len(chat.messages)
    kept_messages: list[ChatMessage] = []
    for msg in chat.messages:
        if msg.id == message_id:
            delete_message_images(chat, msg)
            continue
        kept_messages.append(msg)
    chat.messages = kept_messages
    if len(chat.messages) == before:
        raise HTTPException(status_code=404, detail="message not found")

    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.put("/chats/{chat_id}/messages/{message_id}/save-and-truncate", response_model=Chat)
def save_message_and_truncate(chat_id: str, message_id: str, req: UpdateMessageRequest) -> Chat:
    """保存编辑后的消息并删除该消息之后的所有消息。

    合并 update_message + 逐条 delete_message 为一次 load/save，
    避免多次 HTTP 往返与重复 JSON 读写。
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")

    found_idx: int | None = None
    for i, m in enumerate(chat.messages):
        if m.id == message_id:
            old_images = list(getattr(m, "images", []) or [])
            stored_content = m.content
            m.role = req.role
            m.content = req.content
            if getattr(req, "images", None) is not None:
                m.images = req.images or []
                old_ids = {img.id for img in old_images}
                new_ids = {img.id for img in (m.images or [])}
                for old_img in old_images:
                    if old_img.id not in new_ids:
                        delete_chat_image(chat, old_img)
            if req.characterId is not None:
                m.characterId = req.characterId
            if getattr(req, "senderPersonaId", None) is not None:
                m.senderPersonaId = req.senderPersonaId
            if getattr(req, "senderName", None) is not None:
                m.senderName = req.senderName
            if getattr(req, "senderAvatar", None) is not None:
                m.senderAvatar = req.senderAvatar
            req_dump = req.model_dump(exclude_unset=True)
            if "greetingVariants" in req_dump:
                _apply_greeting_variants_on_update(m, req, req_dump, chat)
            elif "greetingVariantIndex" in req_dump:
                m.greetingVariantIndex = req_dump["greetingVariantIndex"]
                gv = getattr(m, "greetingVariants", None)
                if (
                    isinstance(gv, list)
                    and len(gv) >= 2
                    and isinstance(m.greetingVariantIndex, int)
                    and 0 <= m.greetingVariantIndex < len(gv)
                ):
                    m.content = gv[m.greetingVariantIndex]
                    gvr = getattr(m, "greetingVariantReasoningContents", None)
                    if gvr and isinstance(gvr, list) and 0 <= m.greetingVariantIndex < len(gvr):
                        r0 = (gvr[m.greetingVariantIndex] or "").strip()
                        m.reasoningContent = r0 if r0 else None
            if "reasoningContent" in req_dump:
                m.reasoningContent = req_dump["reasoningContent"]
            if "reasoningDurationSec" in req_dump:
                m.reasoningDurationSec = req_dump["reasoningDurationSec"]
            if m.content != stored_content:
                m.ttsAudioAssetId = None
                m.ttsAudioSourceText = None
            found_idx = i
            break

    if found_idx is None:
        raise HTTPException(status_code=404, detail="message not found")

    # 删除 found_idx 之后的所有消息（含关联图片）
    for msg in chat.messages[found_idx + 1:]:
        delete_message_images(chat, msg)
    chat.messages = chat.messages[:found_idx + 1]
    chat.updatedAt = _now_iso()
    return save_chat(chat)


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: str) -> dict:
    """
    删除聊天会话
    
    Args:
        chat_id: 聊天会话ID
    
    Returns:
        dict: 成功响应 {"ok": True}
    """
    delete_chat(chat_id)
    return {"ok": True}


@router.post("/chats/{chat_id}/images", response_model=UploadChatImagesResponse)
def upload_chat_images(chat_id: str, req: UploadChatImagesRequest) -> UploadChatImagesResponse:
    """上传会话图片，返回附件元数据。

    主聊天当前仅支持图片，且单文件上限与助手图片附件保持一致为 100MB。
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    if not req.images:
        return UploadChatImagesResponse(images=[])
    saved: list[ChatImageAttachment] = []
    for item in req.images:
        try:
            raw = item.imageData
            if "," in raw:
                raw = raw.split(",", 1)[1]
            data = base64.b64decode(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid imageData")
        if not is_image_mime_type(item.mimeType):
            raise HTTPException(status_code=400, detail="main chat only supports image uploads")
        if len(data) > ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES:
            raise HTTPException(status_code=400, detail="image too large")
        attachment = save_chat_image(
            chat=chat,
            data=data,
            mime_type=item.mimeType,
            original_name=item.originalName,
            width=item.width,
            height=item.height,
        )
        saved.append(attachment)
    return UploadChatImagesResponse(images=saved)


@router.get("/chats/{chat_id}/images/{image_id}")
def get_chat_image(chat_id: str, image_id: str) -> FileResponse:
    """读取会话图片文件。"""
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    image: ChatImageAttachment | None = None
    for msg in chat.messages:
        for img in getattr(msg, "images", []) or []:
            if img.id == image_id:
                image = img
                break
        if image:
            break
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    path = chat_image_path(chat.characterId, chat.id, image.filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file not found")
    return FileResponse(path, media_type=image.mimeType or "application/octet-stream")


@router.post("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def add_member(chat_id: str, member_id: str) -> Chat:
    """
    向群聊添加成员
    
    只能向群聊添加成员。会检查角色是否存在，如果成员已存在则不做任何操作。
    
    Args:
        chat_id: 聊天会话ID
        member_id: 要添加的角色ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在、非群聊、角色不存在时抛出相应错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can add members")
    
    try:
        load_character(member_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="character not found")
    
    if member_id not in chat.memberIds:
        chat.memberIds.append(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat


@router.delete("/chats/{chat_id}/members/{member_id}", response_model=Chat)
def remove_member(chat_id: str, member_id: str) -> Chat:
    """
    从群聊移除成员
    
    只能从群聊移除成员。如果成员不存在则不做任何操作。
    
    Args:
        chat_id: 聊天会话ID
        member_id: 要移除的角色ID
    
    Returns:
        Chat: 更新后的聊天对象
    
    Raises:
        HTTPException: 聊天不存在或非群聊时抛出相应错误
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    
    if not chat.isGroup:
        raise HTTPException(status_code=400, detail="only group chats can remove members")
    
    if member_id in chat.memberIds:
        chat.memberIds.remove(member_id)
        chat.updatedAt = _now_iso()
        return save_chat(chat)
    
    return chat
