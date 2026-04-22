"""Chat-scoped assistant tools."""

from __future__ import annotations

import re
from typing import Any

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R
from app.chat_transcript import (
    build_jsonl_header_dict,
    build_transcript_rows_from_messages,
    slice_messages_since_memory_marker,
)
from app.routes.generate import collect_active_worldbooks
from app.schemas import Chat, ChatOverrides, WorldBookAttachment
from app.storage import (
    load_chat,
    load_chat_memory,
    load_character,
    load_settings,
    load_worldbook,
    mark_last_message_memory_updated,
    save_chat,
    save_chat_memory,
)
from app.tokenizer_service import trim_dict_messages_to_token_budget


def _load_chat_ctx(chat_id: str | None) -> Chat | None:
    if not chat_id:
        return None
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        return None


_DATA_IMAGE_B64_RE = re.compile(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+")
_MAX_CONTENT_SANITIZE_LEN = 500_000


def _strip_inline_data_images(text: str) -> str:
    if not text:
        return text
    chunk = text[:_MAX_CONTENT_SANITIZE_LEN]
    rest = text[_MAX_CONTENT_SANITIZE_LEN:]
    chunk = _DATA_IMAGE_B64_RE.sub("[image]", chunk)
    if rest:
        chunk = chunk + _DATA_IMAGE_B64_RE.sub("[image]", rest)
    return chunk


def _sanitize_chat_payload_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        mm = dict(m)
        if mm.get("images"):
            mm["images"] = [{"placeholder": "[image]"}]
        c = mm.get("content")
        if isinstance(c, str):
            c = _strip_inline_data_images(c)
            if len(c) > 8000 and c[:200].startswith("data:image/"):
                c = "[image]"
            mm["content"] = c
        out.append(mm)
    return out


def handle_chat_read_conversation(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_read_conversation")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_read_conversation", details={"chatId": chat_id})

    raw = args.get("range")
    rng = str(raw).strip() if raw is not None and str(raw).strip() != "" else "transcript"

    read_meta: dict[str, Any] = {}
    if rng == "full":
        rng = "transcript"
        read_meta["deprecated"] = {
            "range": "full",
            "useInstead": "transcript",
            "message": "range=full 已弃用，已按 transcript 返回与 JSONL 导出一致的精简正文。",
        }

    if rng not in ("transcript", "since_memory_marker", "debug"):
        return R.err(
            R.VALIDATION_ERROR,
            "range must be transcript, since_memory_marker, debug, or (deprecated) full",
            tool="chat_read_conversation",
        )

    if rng in ("transcript", "since_memory_marker"):
        settings = load_settings()
        src_messages = list(chat.messages)
        if rng == "since_memory_marker":
            src_messages = slice_messages_since_memory_marker(src_messages)
        rows = build_transcript_rows_from_messages(src_messages, settings)
        max_msg = getattr(ctx.assistant_settings, "tool_read_max_messages", None)
        if isinstance(max_msg, int) and max_msg >= 1 and len(rows) > max_msg:
            rows = rows[-max_msg:]

        max_tok = getattr(ctx.assistant_settings, "tool_read_max_tokens", None)
        if isinstance(max_tok, int) and max_tok >= 1:
            rows, tw = trim_dict_messages_to_token_budget(rows, max_tok)
            if tw:
                merged = list(read_meta.get("warnings", [])) if read_meta.get("warnings") else []
                merged.extend(tw)
                read_meta["warnings"] = merged

        data: dict[str, Any] = {
            "mode": "transcript",
            "format": "simpletavern_chat_jsonl",
            "header": build_jsonl_header_dict(chat),
            "messages": rows,
        }
        if read_meta:
            data["readMeta"] = read_meta
        return R.ok(data, tool="chat_read_conversation")

    # range=debug：完整会话 JSON（含 TTS/附件等全部持久化字段），非必要勿用
    payload = chat.model_dump(mode="json")
    messages = list(payload.get("messages") or [])

    max_msg = getattr(ctx.assistant_settings, "tool_read_max_messages", None)
    if isinstance(max_msg, int) and max_msg >= 1 and len(messages) > max_msg:
        messages = messages[-max_msg:]

    messages = _sanitize_chat_payload_messages(messages)

    debug_meta: dict[str, Any] = {}
    max_tok = getattr(ctx.assistant_settings, "tool_read_max_tokens", None)
    if isinstance(max_tok, int) and max_tok >= 1:
        messages, tw = trim_dict_messages_to_token_budget(messages, max_tok)
        if tw:
            debug_meta["warnings"] = tw

    payload["messages"] = messages
    out: dict[str, Any] = {"mode": "debug", "chat": payload}
    if debug_meta:
        out["readMeta"] = debug_meta
    return R.ok(out, tool="chat_read_conversation")


def handle_chat_read_long_term_memory(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_read_long_term_memory")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_read_long_term_memory")
    try:
        memory = load_chat_memory(chat.characterId, chat.id)
    except FileNotFoundError:
        ov = getattr(chat, "overrides", None)
        fallback = (getattr(ov, "longTermMemory", None) or "") if ov is not None else ""
        return R.ok({"chatId": chat_id, "content": fallback}, tool="chat_read_long_term_memory")
    if memory is None:
        ov = getattr(chat, "overrides", None)
        fallback = (getattr(ov, "longTermMemory", None) or "") if ov is not None else ""
        return R.ok({"chatId": chat_id, "content": fallback}, tool="chat_read_long_term_memory")
    return R.ok({"chatId": chat_id, "content": memory}, tool="chat_read_long_term_memory")


def handle_chat_read_character_card(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_read_character_card")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_read_character_card")
    target_id = str(args.get("characterId") or "")
    participant_ids = set(chat.memberIds or [])
    if not participant_ids:
        participant_ids.add(chat.characterId)
    if target_id not in participant_ids:
        return R.err(R.FORBIDDEN, "character not in chat", tool="chat_read_character_card", details={"characterId": target_id})
    try:
        card = load_character(target_id)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "character not found", tool="chat_read_character_card")
    return R.ok({"character": card.model_dump(mode="json")}, tool="chat_read_character_card")


def handle_chat_list_participants(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_list_participants")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_list_participants")
    participant_ids = chat.memberIds if chat.isGroup else [chat.characterId]
    participants = []
    for cid in participant_ids:
        try:
            card = load_character(cid)
            participants.append({"id": cid, "name": card.name, "avatar": card.avatar})
        except FileNotFoundError:
            participants.append({"id": cid, "name": "", "avatar": ""})
    return R.ok({"participants": participants}, tool="chat_list_participants")


def handle_chat_append_long_term_memory(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_write_memory:
        return R.err(R.FORBIDDEN, "memory write not allowed for this request", tool="chat_append_long_term_memory")
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_append_long_term_memory")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_append_long_term_memory")
    content = str(args.get("content") or "").strip()
    current = (getattr(chat.overrides, "longTermMemory", None) or "").strip()
    new_content = (current + "\n" + content).strip() if current else content
    save_chat_memory(chat.characterId, chat.id, new_content)
    chat.overrides.longTermMemory = new_content
    mark_last_message_memory_updated(chat)
    save_chat(chat)
    return R.ok({"chatId": chat_id}, tool="chat_append_long_term_memory")


def handle_chat_overwrite_long_term_memory(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_write_memory:
        return R.err(R.FORBIDDEN, "memory write not allowed for this request", tool="chat_overwrite_long_term_memory")
    if not ctx.allow_destructive_tools:
        return R.err(R.FORBIDDEN, "destructive tools not allowed (overwrite requires destructive)", tool="chat_overwrite_long_term_memory")
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_overwrite_long_term_memory")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_overwrite_long_term_memory")
    content = str(args.get("content") or "")
    save_chat_memory(chat.characterId, chat.id, content)
    chat.overrides.longTermMemory = content
    mark_last_message_memory_updated(chat)
    save_chat(chat)
    return R.ok({"chatId": chat_id}, tool="chat_overwrite_long_term_memory")


def handle_chat_get_worldbook_state(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_get_worldbook_state")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_get_worldbook_state")
    ov = chat.overrides or ChatOverrides()
    attachments = [a.model_dump(mode="json") for a in (ov.worldBookAttachments or [])]
    return R.ok(
        {
            "worldBookIds": list(ov.worldBookIds or []),
            "worldBookAttachments": attachments,
            "worldBookGlobalExclusions": list(ov.worldBookGlobalExclusions or []),
        },
        tool="chat_get_worldbook_state",
    )


def handle_chat_worldbook_global_exclusion_set(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_worldbook_global_exclusion_set")
    wid = str(args.get("worldbookId") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="chat_worldbook_global_exclusion_set")
    if "excluded" not in args or not isinstance(args.get("excluded"), bool):
        return R.err(R.VALIDATION_ERROR, "excluded boolean required", tool="chat_worldbook_global_exclusion_set")
    excluded = bool(args["excluded"])
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_worldbook_global_exclusion_set")
    if chat.overrides is None:
        chat.overrides = ChatOverrides()
    excl = list(chat.overrides.worldBookGlobalExclusions or [])
    if excluded:
        if wid not in excl:
            excl.append(wid)
    else:
        excl = [x for x in excl if x != wid]
    chat.overrides.worldBookGlobalExclusions = list(dict.fromkeys(excl))
    save_chat(chat)
    return R.ok(
        {"chatId": chat_id, "worldBookGlobalExclusions": list(chat.overrides.worldBookGlobalExclusions or [])},
        tool="chat_worldbook_global_exclusion_set",
    )


def handle_chat_worldbook_attachment_add(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_worldbook_attachment_add")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_worldbook_attachment_add")
    wid = str(args.get("worldbookId") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="chat_worldbook_attachment_add")
    try:
        load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="chat_worldbook_attachment_add")
    if chat.overrides is None:
        chat.overrides = ChatOverrides()
    att = list(chat.overrides.worldBookAttachments or [])
    if any(getattr(a, "worldBookId", None) == wid for a in att):
        return R.err(R.CONFLICT, "worldbook already attached", tool="chat_worldbook_attachment_add")
    scan = args.get("scanDepth")
    insert_d = args.get("insertDepth")
    ins = int(insert_d) if insert_d is not None else 5
    ins = max(1, ins)
    att.append(
        WorldBookAttachment(
            worldBookId=wid,
            scanDepth=int(scan) if scan is not None else None,
            insertDepth=ins,
        )
    )
    chat.overrides.worldBookAttachments = att
    chat.overrides._sync_worldbook_attachments()
    save_chat(chat)
    return R.ok({"chatId": chat_id, "worldBookAttachments": [a.model_dump(mode="json") for a in att]}, tool="chat_worldbook_attachment_add")


def handle_chat_worldbook_attachment_remove(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_worldbook_attachment_remove")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_worldbook_attachment_remove")
    wid = str(args.get("worldbookId") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="chat_worldbook_attachment_remove")
    if chat.overrides is None:
        chat.overrides = ChatOverrides()
    att = [a for a in (chat.overrides.worldBookAttachments or []) if getattr(a, "worldBookId", None) != wid]
    if len(att) == len(chat.overrides.worldBookAttachments or []):
        return R.err(R.NOT_FOUND, "attachment not found", tool="chat_worldbook_attachment_remove")
    chat.overrides.worldBookAttachments = att
    chat.overrides._sync_worldbook_attachments()
    save_chat(chat)
    return R.ok({"chatId": chat_id, "worldBookAttachments": [a.model_dump(mode="json") for a in att]}, tool="chat_worldbook_attachment_remove")


def handle_chat_worldbook_attachment_reorder(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_worldbook_attachment_reorder")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_worldbook_attachment_reorder")
    order = args.get("orderedWorldBookIds")
    if not isinstance(order, list):
        return R.err(R.VALIDATION_ERROR, "orderedWorldBookIds array required", tool="chat_worldbook_attachment_reorder")
    ids = [str(x) for x in order]
    if chat.overrides is None:
        chat.overrides = ChatOverrides()
    by_id = {a.worldBookId: a for a in (chat.overrides.worldBookAttachments or [])}
    new_att = [by_id[w] for w in ids if w in by_id]
    for wid, a in by_id.items():
        if wid not in set(ids):
            new_att.append(a)
    chat.overrides.worldBookAttachments = new_att
    chat.overrides._sync_worldbook_attachments()
    save_chat(chat)
    return R.ok({"chatId": chat_id, "worldBookAttachments": [a.model_dump(mode="json") for a in new_att]}, tool="chat_worldbook_attachment_reorder")


def handle_chat_summarize_active_worldbooks(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_summarize_active_worldbooks")
    chat = _load_chat_ctx(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_summarize_active_worldbooks")
    global_excl = set(getattr(chat.overrides, "worldBookGlobalExclusions", []) or [])
    ordered = [a.worldBookId for a in (chat.overrides.worldBookAttachments or [])]
    active = collect_active_worldbooks(chat_id, ordered_ids=ordered, global_exclusions=global_excl)
    summaries = []
    for b in active:
        summaries.append(
            {
                "id": b.id,
                "name": b.name,
                "globalActive": bool(getattr(b, "globalActive", False)),
                "inSessionList": chat_id in (getattr(b, "sessionChatIds", []) or []),
            }
        )
    return R.ok({"activeWorldbooks": summaries, "attachmentOrder": ordered}, tool="chat_summarize_active_worldbooks")
