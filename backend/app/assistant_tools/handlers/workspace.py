"""Workspace file and character card tools."""

from __future__ import annotations

import json
from typing import Any

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools.paths import resolve_ai_path
from app.assistant_tools import result as R
from app.schemas import CharacterCard
from app.storage import save_workspace_character_card, workspace_character_card_path


def handle_workspace_read_file(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    try:
        target = resolve_ai_path(path_str)
    except ValueError as e:
        return R.err(R.VALIDATION_ERROR, str(e), tool="workspace_read_file")
    if not target.exists() or not target.is_file():
        return R.err(R.NOT_FOUND, "file not found", tool="workspace_read_file", details={"path": path_str})
    content = target.read_text(encoding="utf-8")
    return R.ok({"path": path_str, "content": content}, tool="workspace_read_file")


def handle_workspace_create_file(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    try:
        target = resolve_ai_path(path_str)
    except ValueError as e:
        return R.err(R.VALIDATION_ERROR, str(e), tool="workspace_create_file")
    if target.exists():
        return R.err(R.CONFLICT, "file already exists", tool="workspace_create_file", details={"path": path_str})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return R.ok({"path": path_str}, tool="workspace_create_file")


def handle_workspace_write_file(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    path_str = str(args.get("path") or "")
    content = str(args.get("content") or "")
    try:
        target = resolve_ai_path(path_str)
    except ValueError as e:
        return R.err(R.VALIDATION_ERROR, str(e), tool="workspace_write_file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return R.ok({"path": path_str}, tool="workspace_write_file")


def handle_workspace_delete_file(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_destructive_tools:
        return R.err(R.FORBIDDEN, "destructive tools not allowed for this request", tool="workspace_delete_file")
    path_str = str(args.get("path") or "")
    try:
        target = resolve_ai_path(path_str)
    except ValueError as e:
        return R.err(R.VALIDATION_ERROR, str(e), tool="workspace_delete_file")
    if target.exists() and target.is_file():
        target.unlink(missing_ok=True)
    return R.ok({"path": path_str}, tool="workspace_delete_file")


def _workspace_card_raw() -> dict[str, Any] | None:
    p = workspace_character_card_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def handle_workspace_patch_character_card(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict) or not args:
        return R.err(R.VALIDATION_ERROR, "expected non-empty object with fields to patch", tool="workspace_patch_character_card")
    raw = _workspace_card_raw()
    if raw is None:
        return R.err(R.NOT_FOUND, "workspace character_card.json not found", tool="workspace_patch_character_card")
    merged = dict(raw)
    for key, val in args.items():
        if val is None:
            continue
        if val == "":
            return R.err(
                R.VALIDATION_ERROR,
                "empty string is not allowed in patch fields",
                tool="workspace_patch_character_card",
                details={"field": key},
            )
        merged[key] = val
    try:
        card = CharacterCard.model_validate(merged)
    except Exception as e:
        return R.err(R.UPSTREAM_VALIDATION, str(e), tool="workspace_patch_character_card")
    save_workspace_character_card(card)
    return R.ok({"path": "character_card.json", "card": card.model_dump(mode="json")}, tool="workspace_patch_character_card")


def handle_workspace_replace_character_card(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_destructive_tools:
        return R.err(R.FORBIDDEN, "destructive tools not allowed for this request", tool="workspace_replace_character_card")
    raw = args.get("card")
    if raw is None and isinstance(args.get("content"), str):
        try:
            raw = json.loads(str(args.get("content")))
        except Exception:
            raw = None
    if not isinstance(raw, dict):
        return R.err(R.VALIDATION_ERROR, "card object required", tool="workspace_replace_character_card")
    try:
        card = CharacterCard.model_validate(raw)
    except Exception as e:
        return R.err(R.UPSTREAM_VALIDATION, str(e), tool="workspace_replace_character_card")
    save_workspace_character_card(card)
    return R.ok({"path": "character_card.json", "card": card.model_dump(mode="json")}, tool="workspace_replace_character_card")
