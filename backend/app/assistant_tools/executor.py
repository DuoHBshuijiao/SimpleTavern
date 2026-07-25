"""Execute assistant tools: validation, outcomes, SSE hints, workspace card for SSE."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError
from jsonschema.validators import validator_for

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.digest import args_digest
from app.assistant_tools import result as R
from app.assistant_tools.registry import tool_entry
from app.schemas import CharacterCard
from app.storage import load_chat

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionOutcome:
    result: dict[str, Any]
    card: dict[str, Any] | None
    chat_memory_updated: dict[str, Any] | None
    worldbook_updated: dict[str, Any] | None
    chat_overrides_updated: dict[str, Any] | None


def _empty_outcome(result: dict[str, Any]) -> ToolExecutionOutcome:
    return ToolExecutionOutcome(
        result=result,
        card=None,
        chat_memory_updated=None,
        worldbook_updated=None,
        chat_overrides_updated=None,
    )


def _try_parse_character_card_from_workspace(path_str: str, content: str | None) -> dict[str, Any] | None:
    if Path(path_str).name != "character_card.json":
        return None
    raw: Any
    try:
        raw = json.loads(content) if content is not None else None
    except Exception as exc:
        logger.debug("workspace character_card.json JSON parse failed: %s", exc)
        return None
    if raw is None:
        return None
    try:
        card = CharacterCard.model_validate(raw)
    except Exception as exc:
        logger.debug("workspace character_card.json schema invalid: %s", exc)
        return None
    return card.model_dump(mode="json")


def _validate_json_schema(schema: dict[str, Any], args: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    """Return VALIDATION_ERROR result dict or None if ok."""
    try:
        cls = validator_for(schema)
        cls(schema).validate(args)
    except ValidationError as e:
        return R.err(
            R.VALIDATION_ERROR,
            getattr(e, "message", None) or str(e),
            tool=tool_name,
            details={"path": list(e.path), "validator": getattr(e, "validator", None)},
        )
    except Exception as e:
        return R.err(R.VALIDATION_ERROR, str(e), tool=tool_name)
    return None


def _worldbook_sse_payload(name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    if not result.get("ok"):
        return None
    data = result.get("data") or {}
    if name == "worldbook_create":
        w = data.get("worldbook")
        if isinstance(w, dict) and w.get("id"):
            return {"worldbookId": w["id"]}
        return None
    if name == "worldbook_delete":
        did = data.get("deletedId")
        if did:
            return {"worldbookId": did}
        return None
    if name in (
        "worldbook_update_meta",
        "worldbook_entry_add",
        "worldbook_entry_update",
        "worldbook_entry_delete",
    ):
        wid = str(args.get("worldbookId") or args.get("id") or "")
        if wid:
            return {"worldbookId": wid}
    return None


def _chat_overrides_sse_payload(name: str, ctx: AssistantToolContext, result: dict[str, Any]) -> dict[str, Any] | None:
    if not result.get("ok") or not ctx.chat_id:
        return None
    if name in (
        "chat_append_long_term_memory",
        "chat_overwrite_long_term_memory",
        "chat_worldbook_attachment_add",
        "chat_worldbook_attachment_remove",
        "chat_worldbook_attachment_reorder",
        "chat_worldbook_global_exclusion_set",
        "chat_content_regex_manage",
        "character_content_regex_manage",
    ):
        return {"chatId": ctx.chat_id}
    return None


def execute_tool(
    name: str,
    args: dict[str, Any],
    ctx: AssistantToolContext,
) -> ToolExecutionOutcome:
    t0 = time.perf_counter()
    ad = args_digest(args if isinstance(args, dict) else {})

    if not isinstance(args, dict):
        res = R.err(
            R.VALIDATION_ERROR,
            "tool arguments must be an object",
            tool=name,
            details={"kind": "tool_call_invalid"},
        )
        _log_tool_end(name, t0, res, ad)
        return _empty_outcome(res)

    entry = tool_entry(name)
    if entry is None:
        res = R.err(R.UNKNOWN_TOOL, f"unknown tool: {name}", tool=name)
        _log_tool_end(name, t0, res, ad)
        return _empty_outcome(res)

    if not entry.skip_jsonschema:
        verr = _validate_json_schema(entry.parameters, args, entry.name)
        if verr is not None:
            _log_tool_end(name, t0, verr, ad)
            return _empty_outcome(verr)

    fn = entry.handler
    try:
        result = fn(ctx, args)
    except Exception as exc:
        logger.exception("assistant tool handler failed: %s", name)
        res = R.err(R.INTERNAL, "internal error", tool=name, details={"kind": "internal"})
        _log_tool_end(name, t0, res, ad)
        return _empty_outcome(res)

    _log_tool_end(name, t0, result, ad)

    card: dict[str, Any] | None = None
    if name == "workspace_write_file" and result.get("ok"):
        path_str = str(args.get("path") or "")
        content = str(args.get("content") or "")
        card = _try_parse_character_card_from_workspace(path_str, content)
    elif name == "workspace_replace_character_card" and result.get("ok"):
        data = result.get("data") or {}
        c = data.get("card")
        if isinstance(c, dict):
            card = c
    elif name == "workspace_patch_character_card" and result.get("ok"):
        data = result.get("data") or {}
        c = data.get("card")
        if isinstance(c, dict):
            card = c

    mem_update: dict[str, Any] | None = None
    if name in ("chat_append_long_term_memory", "chat_overwrite_long_term_memory") and result.get("ok") and ctx.chat_id:
        try:
            mem_update = load_chat(ctx.chat_id).model_dump(mode="json")
        except Exception:
            mem_update = None

    wb_sse = _worldbook_sse_payload(name, args, result)
    co_sse = _chat_overrides_sse_payload(name, ctx, result)

    return ToolExecutionOutcome(
        result=result,
        card=card,
        chat_memory_updated=mem_update,
        worldbook_updated=wb_sse,
        chat_overrides_updated=co_sse,
    )


def _log_tool_end(name: str, t0: float, result: dict[str, Any], ad: str) -> None:
    ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "assistant_tool name=%s ok=%s code=%s ms=%.2f args_digest=%s",
        name,
        result.get("ok"),
        result.get("code"),
        ms,
        ad,
    )


# Re-export for routes that import from executor
from app.assistant_tools.registry import build_openai_tools_list  # noqa: E402,F401
