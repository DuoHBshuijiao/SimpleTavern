"""World book library tools."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R
from app.schemas import WorldBook, WorldBookEntry
from app.storage import (
    delete_worldbook,
    list_characters,
    list_worldbooks,
    load_worldbook,
    save_character,
    save_worldbook,
)


def handle_worldbook_list(_ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    books = list_worldbooks()
    return R.ok(
        {"worldbooks": [{"id": b.id, "name": b.name, "globalActive": b.globalActive, "sessionChatIds": b.sessionChatIds} for b in books]},
        tool="worldbook_list",
    )


def handle_worldbook_get(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    wid = str(args.get("worldbookId") or args.get("id") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="worldbook_get")
    try:
        book = load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_get")
    return R.ok({"worldbook": book.model_dump(mode="json")}, tool="worldbook_get")


def handle_worldbook_create(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        return R.err(R.VALIDATION_ERROR, "name required", tool="worldbook_create")
    book = WorldBook(name=name)
    save_worldbook(book)
    return R.ok({"worldbook": book.model_dump(mode="json")}, tool="worldbook_create")


def handle_worldbook_update_meta(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    wid = str(args.get("worldbookId") or args.get("id") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="worldbook_update_meta")
    try:
        book = load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_update_meta")
    if "name" in args and args["name"] is not None:
        book.name = str(args["name"])
    if "globalActive" in args and args["globalActive"] is not None:
        book.globalActive = bool(args["globalActive"])
    if "sessionChatIds" in args and args["sessionChatIds"] is not None:
        book.sessionChatIds = list(args["sessionChatIds"])
    save_worldbook(book)
    return R.ok({"worldbook": book.model_dump(mode="json")}, tool="worldbook_update_meta")


def _cascade_remove_worldbook_from_characters(worldbook_id: str) -> None:
    for card in list_characters():
        ids = list(getattr(card, "attachedWorldBookIds", []) or [])
        if worldbook_id not in ids:
            continue
        card.attachedWorldBookIds = [i for i in ids if i != worldbook_id]
        save_character(card)


def handle_worldbook_delete(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_destructive_tools:
        return R.err(R.FORBIDDEN, "destructive tools not allowed for this request", tool="worldbook_delete")
    wid = str(args.get("worldbookId") or args.get("id") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="worldbook_delete")
    try:
        load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_delete")
    _cascade_remove_worldbook_from_characters(wid)
    delete_worldbook(wid)
    return R.ok({"deletedId": wid}, tool="worldbook_delete")


def handle_worldbook_entry_add(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    wid = str(args.get("worldbookId") or "")
    if not wid:
        return R.err(R.VALIDATION_ERROR, "worldbookId required", tool="worldbook_entry_add")
    try:
        book = load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_entry_add")
    entry_data = {k: v for k, v in args.items() if k != "worldbookId"}
    if "id" not in entry_data or not entry_data.get("id"):
        entry_data["id"] = uuid4().hex
    try:
        entry = WorldBookEntry.model_validate(entry_data)
    except (ValueError, ValidationError) as e:
        return R.err(R.UPSTREAM_VALIDATION, str(e), tool="worldbook_entry_add")
    book.entries.append(entry)
    save_worldbook(book)
    return R.ok({"worldbookId": wid, "entry": entry.model_dump(mode="json")}, tool="worldbook_entry_add")


def handle_worldbook_entry_update(_ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    wid = str(args.get("worldbookId") or "")
    eid = str(args.get("entryId") or "")
    if not wid or not eid:
        return R.err(R.VALIDATION_ERROR, "worldbookId and entryId required", tool="worldbook_entry_update")
    try:
        book = load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_entry_update")
    found = None
    for i, e in enumerate(book.entries):
        if e.id == eid:
            found = i
            break
    if found is None:
        return R.err(R.NOT_FOUND, "entry not found", tool="worldbook_entry_update")
    cur = book.entries[found].model_dump()
    for k, v in args.items():
        if k in ("worldbookId", "entryId"):
            continue
        if v is not None:
            cur[k] = v
    try:
        book.entries[found] = WorldBookEntry.model_validate(cur)
    except (ValueError, ValidationError) as e:
        return R.err(R.UPSTREAM_VALIDATION, str(e), tool="worldbook_entry_update")
    save_worldbook(book)
    return R.ok({"worldbookId": wid, "entry": book.entries[found].model_dump(mode="json")}, tool="worldbook_entry_update")


def handle_worldbook_entry_delete(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.allow_destructive_tools:
        return R.err(R.FORBIDDEN, "destructive tools not allowed for this request", tool="worldbook_entry_delete")
    wid = str(args.get("worldbookId") or "")
    eid = str(args.get("entryId") or "")
    if not wid or not eid:
        return R.err(R.VALIDATION_ERROR, "worldbookId and entryId required", tool="worldbook_entry_delete")
    try:
        book = load_worldbook(wid)
    except FileNotFoundError:
        return R.err(R.NOT_FOUND, "worldbook not found", tool="worldbook_entry_delete")
    new_entries = [e for e in book.entries if e.id != eid]
    if len(new_entries) == len(book.entries):
        return R.err(R.NOT_FOUND, "entry not found", tool="worldbook_entry_delete")
    book.entries = new_entries
    save_worldbook(book)
    return R.ok({"worldbookId": wid, "deletedEntryId": eid}, tool="worldbook_entry_delete")
