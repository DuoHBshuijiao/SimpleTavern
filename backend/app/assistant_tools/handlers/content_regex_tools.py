"""会话正文正则与会话绑定角色卡正则的 CRUD（助手与 MVU Agent 共用）。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R
from app.schemas import ChatContentRegexRule
from app.storage import load_chat, load_character, save_chat, save_character

_MAX_RULES = 100


def _now_iso() -> str:
    from app.schemas import _now_iso as schema_now_iso

    return schema_now_iso()


def _renumber_rules(rules: list[ChatContentRegexRule]) -> list[ChatContentRegexRule]:
    sorted_rules = sorted(rules, key=lambda r: (r.order, r.id))
    return [r.model_copy(update={"order": i}) for i, r in enumerate(sorted_rules)]


def handle_chat_content_regex_manage(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """管理当前会话的 overrides.contentRegexRules。"""
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="chat_content_regex_manage")
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "chat not found", tool="chat_content_regex_manage", details={"chatId": chat_id})

    op = str(args.get("operation") or "").strip().lower()
    if op not in ("list", "upsert", "delete"):
        return R.err(
            R.VALIDATION_ERROR,
            "operation must be list, upsert, or delete",
            tool="chat_content_regex_manage",
        )

    rules = list(chat.overrides.contentRegexRules or [])

    if op == "list":
        data = [r.model_dump(mode="json") for r in rules]
        return R.ok({"rules": data, "count": len(data)}, tool="chat_content_regex_manage")

    if op == "delete":
        rid = str(args.get("rule_id") or "").strip()
        if not rid:
            return R.err(R.VALIDATION_ERROR, "rule_id is required for delete", tool="chat_content_regex_manage")
        new_rules = [r for r in rules if r.id != rid]
        if len(new_rules) == len(rules):
            return R.err(R.NOT_FOUND, "rule not found", tool="chat_content_regex_manage", details={"ruleId": rid})
        chat.overrides.contentRegexRules = _renumber_rules(new_rules)
        chat.updatedAt = _now_iso()
        save_chat(chat)
        return R.ok(
            {"deletedId": rid, "rules": [r.model_dump(mode="json") for r in chat.overrides.contentRegexRules]},
            tool="chat_content_regex_manage",
        )

    raw_rule = args.get("rule")
    if not isinstance(raw_rule, dict):
        return R.err(R.VALIDATION_ERROR, "rule object is required for upsert", tool="chat_content_regex_manage")

    rid_in = str(raw_rule.get("id") or "").strip()
    if rid_in:
        idx = next((i for i, r in enumerate(rules) if r.id == rid_in), None)
        if idx is None:
            return R.err(
                R.NOT_FOUND,
                "rule id not found for upsert",
                tool="chat_content_regex_manage",
                details={"ruleId": rid_in},
            )
        base = rules[idx].model_dump(mode="json")
        base.update(raw_rule)
        try:
            merged = ChatContentRegexRule.model_validate(base)
        except Exception as e:
            return R.err(R.VALIDATION_ERROR, str(e), tool="chat_content_regex_manage")
        rules[idx] = merged
    else:
        nr = dict(raw_rule)
        nr.setdefault("id", uuid4().hex)
        try:
            merged = ChatContentRegexRule.model_validate(nr)
        except Exception as e:
            return R.err(R.VALIDATION_ERROR, str(e), tool="chat_content_regex_manage")
        if len(rules) >= _MAX_RULES:
            return R.err(
                R.VALIDATION_ERROR,
                f"rules exceed limit {_MAX_RULES}",
                tool="chat_content_regex_manage",
            )
        rules.append(merged)

    chat.overrides.contentRegexRules = _renumber_rules(rules)
    chat.updatedAt = _now_iso()
    save_chat(chat)
    return R.ok(
        {"rules": [r.model_dump(mode="json") for r in chat.overrides.contentRegexRules]},
        tool="chat_content_regex_manage",
    )


def handle_character_content_regex_manage(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """管理当前会话绑定角色（chat.characterId）的 CharacterCard.contentRegexRules。"""
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="character_content_regex_manage")
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "chat not found", tool="character_content_regex_manage", details={"chatId": chat_id})

    cid = (chat.characterId or "").strip()
    if not cid:
        return R.err(R.VALIDATION_ERROR, "chat has no characterId", tool="character_content_regex_manage")

    try:
        card = load_character(cid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "character not found", tool="character_content_regex_manage", details={"characterId": cid})

    op = str(args.get("operation") or "").strip().lower()
    if op not in ("list", "upsert", "delete"):
        return R.err(
            R.VALIDATION_ERROR,
            "operation must be list, upsert, or delete",
            tool="character_content_regex_manage",
        )

    rules = list(card.contentRegexRules or [])

    if op == "list":
        data = [r.model_dump(mode="json") for r in rules]
        return R.ok({"characterId": cid, "rules": data, "count": len(data)}, tool="character_content_regex_manage")

    if op == "delete":
        rid = str(args.get("rule_id") or "").strip()
        if not rid:
            return R.err(R.VALIDATION_ERROR, "rule_id is required for delete", tool="character_content_regex_manage")
        new_rules = [r for r in rules if r.id != rid]
        if len(new_rules) == len(rules):
            return R.err(R.NOT_FOUND, "rule not found", tool="character_content_regex_manage", details={"ruleId": rid})
        card.contentRegexRules = _renumber_rules(new_rules)
        card.updatedAt = _now_iso()
        save_character(card)
        return R.ok(
            {
                "characterId": cid,
                "deletedId": rid,
                "rules": [r.model_dump(mode="json") for r in card.contentRegexRules],
            },
            tool="character_content_regex_manage",
        )

    raw_rule = args.get("rule")
    if not isinstance(raw_rule, dict):
        return R.err(R.VALIDATION_ERROR, "rule object is required for upsert", tool="character_content_regex_manage")

    rid_in = str(raw_rule.get("id") or "").strip()
    if rid_in:
        idx = next((i for i, r in enumerate(rules) if r.id == rid_in), None)
        if idx is None:
            return R.err(
                R.NOT_FOUND,
                "rule id not found for upsert",
                tool="character_content_regex_manage",
                details={"ruleId": rid_in},
            )
        base = rules[idx].model_dump(mode="json")
        base.update(raw_rule)
        try:
            merged = ChatContentRegexRule.model_validate(base)
        except Exception as e:
            return R.err(R.VALIDATION_ERROR, str(e), tool="character_content_regex_manage")
        rules[idx] = merged
    else:
        nr = dict(raw_rule)
        nr.setdefault("id", uuid4().hex)
        try:
            merged = ChatContentRegexRule.model_validate(nr)
        except Exception as e:
            return R.err(R.VALIDATION_ERROR, str(e), tool="character_content_regex_manage")
        if len(rules) >= _MAX_RULES:
            return R.err(
                R.VALIDATION_ERROR,
                f"rules exceed limit {_MAX_RULES}",
                tool="character_content_regex_manage",
            )
        rules.append(merged)

    card.contentRegexRules = _renumber_rules(rules)
    card.updatedAt = _now_iso()
    save_character(card)
    return R.ok(
        {"characterId": cid, "rules": [r.model_dump(mode="json") for r in card.contentRegexRules]},
        tool="character_content_regex_manage",
    )
