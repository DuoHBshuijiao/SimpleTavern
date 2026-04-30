"""MVU state_variables domain tool handlers — 仅限 MVU Agent 调用的 4 个工具。

聊天助手用的 read_mvu_logs / patch_state_variable 在 chat.py 中。
"""

from __future__ import annotations

from typing import Any

from app.assistant_tools.context import AssistantToolContext
from app.assistant_tools import result as R
from app.content_regex_queue import peek_queue
from app.schemas import StatusTableDef, StatusTableRow, StateVariables
from app.storage import load_chat, save_chat_state_variables


def _load_chat_safe(chat_id: str | None):
    if not chat_id:
        return None
    try:
        return load_chat(chat_id)
    except FileNotFoundError:
        return None


def _render_tables_markdown(tables: list[StatusTableDef]) -> str:
    """将状态表格列表渲染为 markdown，与 prompt_xml 格式一致但不含 XML 包裹。"""
    if not tables:
        return "（暂无状态变量）"
    parts: list[str] = []
    for table in tables:
        columns = list(table.columns or [])
        rows = list(table.rows or [])
        if not rows:
            continue
        lines: list[str] = []
        name = (table.name or "").strip()
        if name:
            lines.append(f"## {name}")
        if columns:
            header = "| field | " + " | ".join(columns) + " |"
            lines.append(header)
            sep = "|---|" + "|".join("---" for _ in columns) + "|"
            lines.append(sep)
        for row in rows:
            field = (row.field or "")
            cell_vals = " | ".join(str(row.cells.get(c, "")) for c in columns) if columns else ""
            lines.append(f"| {field} | {cell_vals} |")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) if parts else "（暂无状态变量）"


def set_cell_in_state(state: StateVariables, table_name: str, field: str, column: str, value: str, *, source: str) -> StateVariables:
    """在 state 中写入一个单元格（纯逻辑、无 IO），供 mvu_set_cell 与 chat.patch_state_variable 复用。

    若 table/row/column 不存在则自动创建，返回原地修改后的 state。
    """
    tables = list(state.tables)
    table_idx = next((i for i, t in enumerate(tables) if (t.name or "") == table_name), None)

    if table_idx is not None:
        table = tables[table_idx]
    else:
        table = StatusTableDef(name=table_name, columns=[], rows=[])
        tables.append(table)
        table_idx = len(tables) - 1

    columns = list(table.columns or [])
    if column not in columns:
        columns.append(column)
    table.columns = columns

    rows = list(table.rows or [])
    row_idx = next((i for i, r in enumerate(rows) if (r.field or "") == field), None)
    if row_idx is not None:
        cells = dict(rows[row_idx].cells or {})
        cells[column] = value
        rows[row_idx] = StatusTableRow(field=field, cells=cells)
    else:
        rows.append(StatusTableRow(field=field, cells={column: value}))

    table.rows = rows
    tables[table_idx] = table
    state.tables = tables
    state.source = source
    return state


def handle_mvu_get_session_state(ctx: AssistantToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="mvu_get_session_state")
    chat = _load_chat_safe(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="mvu_get_session_state", details={"chatId": chat_id})
    state = chat.stateVariables
    tables = list(state.tables) if state else []
    queue_items = peek_queue(chat_id, 50)
    queue_text = "\n".join(
        f"- [{it.get('ruleName', '')}] {it.get('value', '')} (action={it.get('action', '')})"
        for it in queue_items
    ) if queue_items else "（队列为空）"
    return R.ok({
        "stateVariables": state.model_dump(mode="json") if state else None,
        "stateMarkdown": _render_tables_markdown(tables),
        "queueSize": len(queue_items),
        "queueItems": queue_items,
        "queueText": queue_text,
        "version": state.version if state else 0,
    }, tool="mvu_get_session_state")


def handle_mvu_define_table(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="mvu_define_table")
    chat = _load_chat_safe(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="mvu_define_table", details={"chatId": chat_id})

    table_name = str(args.get("table_name") or "").strip()
    if not table_name:
        return R.err(R.VALIDATION_ERROR, "table_name is required", tool="mvu_define_table")
    columns_raw = args.get("columns")
    if not isinstance(columns_raw, list) or not columns_raw:
        return R.err(R.VALIDATION_ERROR, "columns must be a non-empty list of strings", tool="mvu_define_table")
    columns = [str(c).strip() for c in columns_raw]
    if any(not c for c in columns):
        return R.err(R.VALIDATION_ERROR, "column names must be non-empty strings", tool="mvu_define_table")
    fields_raw = args.get("fields")
    if not isinstance(fields_raw, list):
        fields_raw = []
    fields = [str(f).strip() for f in fields_raw if str(f).strip()]

    state = chat.stateVariables or StateVariables()
    tables = list(state.tables)

    existing_idx = next((i for i, t in enumerate(tables) if (t.name or "") == table_name), None)
    new_table = StatusTableDef(
        name=table_name,
        columns=columns,
        rows=[StatusTableRow(field=f, cells={}) for f in fields],
    )
    if existing_idx is not None:
        tables[existing_idx] = new_table
    else:
        tables.append(new_table)

    state.tables = tables
    updated = save_chat_state_variables(chat_id, state)
    return R.ok({
        "table": new_table.model_dump(mode="json"),
        "version": updated.stateVariables.version if updated.stateVariables else 0,
    }, tool="mvu_define_table")


def handle_mvu_set_cell(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="mvu_set_cell")
    chat = _load_chat_safe(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="mvu_set_cell", details={"chatId": chat_id})

    table_name = str(args.get("table_name") or "").strip()
    field = str(args.get("field") or "").strip()
    column = str(args.get("column") or "").strip()
    value = str(args.get("value") or "")

    if not table_name:
        return R.err(R.VALIDATION_ERROR, "table_name is required", tool="mvu_set_cell")
    if not field:
        return R.err(R.VALIDATION_ERROR, "field is required", tool="mvu_set_cell")
    if not column:
        return R.err(R.VALIDATION_ERROR, "column is required", tool="mvu_set_cell")

    state = chat.stateVariables
    if not state:
        return R.err(R.NOT_FOUND, "no stateVariables defined yet; call mvu_define_table first", tool="mvu_set_cell")

    state = set_cell_in_state(state, table_name, field, column, value, source="mvu_agent")
    updated = save_chat_state_variables(chat_id, state)
    return R.ok({
        "tableName": table_name,
        "field": field,
        "column": column,
        "value": value,
        "version": updated.stateVariables.version if updated.stateVariables else 0,
    }, tool="mvu_set_cell")


def handle_mvu_get_chat_context(ctx: AssistantToolContext, args: dict[str, Any]) -> dict[str, Any]:
    chat_id = ctx.chat_id
    if not chat_id:
        return R.err(R.FORBIDDEN, "chat context required", tool="mvu_get_chat_context")
    chat = _load_chat_safe(chat_id)
    if chat is None:
        return R.err(R.NOT_FOUND, "chat not found", tool="mvu_get_chat_context", details={"chatId": chat_id})

    raw = args.get("count")
    try:
        count = max(1, min(50, int(raw)))
    except (TypeError, ValueError):
        count = 10

    recent = chat.messages[-count:] if len(chat.messages) > count else chat.messages
    lines: list[str] = []
    for m in recent:
        role = m.role or "unknown"
        content = (m.content or "").strip()
        if not content:
            continue
        if role == "user":
            label = "用户"
        elif role == "assistant":
            label = "角色"
        else:
            label = role
        lines.append(f"[{label}]: {content}")
    context_text = "\n\n".join(lines) if lines else "（暂无对话上下文）"

    return R.ok({
        "count": len(recent),
        "messages": [{"role": m.role, "content": m.content, "id": m.id} for m in recent],
        "contextMarkdown": context_text,
    }, tool="mvu_get_chat_context")
