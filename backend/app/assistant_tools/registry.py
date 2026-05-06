"""Single registry for assistant tools: metadata, OpenAI function defs, handler lookup."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ToolScope(str, Enum):
    """Logical scope for documentation; filtering uses needs_chat / flags on each tool."""

    WORKSPACE = "workspace"
    CHAT = "chat"
    GLOBAL = "global"


class ToolRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    needs_chat: bool
    needs_memory_write: bool
    needs_destructive: bool
    handler: Callable[..., dict[str, Any]]
    scopes: frozenset[ToolScope]
    risk: ToolRisk
    skip_jsonschema: bool = False


def _fn(
    name: str,
    description: str,
    parameters: dict[str, Any],
    *,
    needs_chat: bool,
    needs_memory_write: bool,
    needs_destructive: bool,
    handler: Callable[..., dict[str, Any]],
    scopes: frozenset[ToolScope],
    risk: ToolRisk,
    skip_jsonschema: bool = False,
) -> RegisteredTool:
    return RegisteredTool(
        name=name,
        description=description,
        parameters=parameters,
        needs_chat=needs_chat,
        needs_memory_write=needs_memory_write,
        needs_destructive=needs_destructive,
        handler=handler,
        scopes=scopes,
        risk=risk,
        skip_jsonschema=skip_jsonschema,
    )


def _openai_def(rt: RegisteredTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": rt.name,
            "description": rt.description,
            "parameters": rt.parameters,
        },
    }


def _all_registered() -> list[RegisteredTool]:
    from app.assistant_tools.handlers import HANDLERS as H

    WS = ToolScope.WORKSPACE
    CH = ToolScope.CHAT
    GL = ToolScope.GLOBAL

    return [
        _fn(
            "core_get_time",
            "返回当前本地时间（YYYY/MM/DD - HH:MM:SS）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["core_get_time"],
            scopes=frozenset({WS, GL}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "workspace_read_file",
            "读取 data/ai_workspace/ 下文件的文本内容。",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对路径，如 character_card.json"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["workspace_read_file"],
            scopes=frozenset({WS}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "workspace_create_file",
            "在 ai_workspace 下新建文件（已存在则失败）。",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["workspace_create_file"],
            scopes=frozenset({WS}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "workspace_write_file",
            "写入或覆盖 ai_workspace 下文件。",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["workspace_write_file"],
            scopes=frozenset({WS}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "workspace_delete_file",
            "删除 ai_workspace 下的文件（破坏性，需用户开启破坏性工具）。",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=True,
            handler=H["workspace_delete_file"],
            scopes=frozenset({WS}),
            risk=ToolRisk.DESTRUCTIVE,
        ),
        _fn(
            "workspace_patch_character_card",
            "按字段合并更新工作区 character_card.json；未出现的键不修改；禁止用空字符串清空 avatar/id/createdAt。",
            {"type": "object", "properties": {}, "additionalProperties": True},
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["workspace_patch_character_card"],
            scopes=frozenset({WS}),
            risk=ToolRisk.WRITE,
            skip_jsonschema=True,
        ),
        _fn(
            "workspace_replace_character_card",
            "整卡覆盖工作区 character_card.json（破坏性）。参数 card 为完整角色卡对象。",
            {
                "type": "object",
                "properties": {"card": {"type": "object"}},
                "required": ["card"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=True,
            handler=H["workspace_replace_character_card"],
            scopes=frozenset({WS}),
            risk=ToolRisk.DESTRUCTIVE,
        ),
        _fn(
            "chat_read_conversation",
            (
                "读取主会话。默认/推荐：range=transcript 或与导出 JSONL 相同的精简结构（"
                "header + messages，每条仅 role/name/content，无 TTS 与多余元数据，省 token）。"
                "自记忆更新标记起用 since_memory_marker。"
                "range=debug 时返回整段会话的完整 JSON（与磁盘 chat 结构一致、体积大），"
                "仅排障或确需全字段时使用；非必要不要选。"
                "已弃用：full 等同于 transcript，将在 readMeta 中提示。"
            ),
            {
                "type": "object",
                "properties": {
                    "range": {
                        "type": "string",
                        "enum": ["transcript", "since_memory_marker", "debug", "full"],
                        "description": (
                            "transcript=精简正文（默认，省略时同此）；"
                            "since_memory_marker=自记忆已更新标记起的精简正文；"
                            "debug=完整会话对象 JSON（大，非必要勿用）；"
                            "full=已弃用，与 transcript 相同"
                        ),
                    }
                },
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_read_conversation"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_read_long_term_memory",
            "读取当前会话长期记忆文本。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_read_long_term_memory"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_read_character_card",
            "读取当前会话参与角色的角色卡（仅参与者）。",
            {
                "type": "object",
                "properties": {"characterId": {"type": "string"}},
                "required": ["characterId"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_read_character_card"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_list_participants",
            "列出当前会话参与者及角色名（顺序与 memberIds 一致）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_list_participants"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_append_long_term_memory",
            "在长期记忆末尾追加内容（需开启记忆写入）。",
            {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=True,
            needs_destructive=False,
            handler=H["chat_append_long_term_memory"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "chat_overwrite_long_term_memory",
            "覆盖全部长期记忆（需记忆写入 + 破坏性工具）。",
            {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=True,
            needs_destructive=True,
            handler=H["chat_overwrite_long_term_memory"],
            scopes=frozenset({CH}),
            risk=ToolRisk.DESTRUCTIVE,
        ),
        _fn(
            "worldbook_list",
            "列出图书馆中所有世界书摘要。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_list"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "worldbook_get",
            "按 ID 读取完整世界书 JSON。",
            {
                "type": "object",
                "properties": {"worldbookId": {"type": "string"}},
                "required": ["worldbookId"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_get"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "worldbook_create",
            "新建世界书。",
            {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_create"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "worldbook_update_meta",
            "更新世界书元数据（名称、globalActive、sessionChatIds 等）。",
            {
                "type": "object",
                "properties": {
                    "worldbookId": {"type": "string"},
                    "name": {"type": "string"},
                    "globalActive": {"type": "boolean"},
                    "sessionChatIds": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["worldbookId"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_update_meta"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "worldbook_delete",
            "删除世界书（级联从角色卡移除引用；破坏性）。",
            {
                "type": "object",
                "properties": {"worldbookId": {"type": "string"}},
                "required": ["worldbookId"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=True,
            handler=H["worldbook_delete"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.DESTRUCTIVE,
        ),
        _fn(
            "worldbook_entry_add",
            "向世界书追加条目。",
            {
                "type": "object",
                "properties": {
                    "worldbookId": {"type": "string"},
                    "title": {"type": "string"},
                    "regex": {"type": "string"},
                    "content": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["worldbookId"],
                "additionalProperties": True,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_entry_add"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "worldbook_entry_update",
            "更新世界书中的某一条目。",
            {
                "type": "object",
                "properties": {
                    "worldbookId": {"type": "string"},
                    "entryId": {"type": "string"},
                    "title": {"type": "string"},
                    "regex": {"type": "string"},
                    "content": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["worldbookId", "entryId"],
                "additionalProperties": True,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["worldbook_entry_update"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "worldbook_entry_delete",
            "删除世界书中的条目（破坏性）。",
            {
                "type": "object",
                "properties": {"worldbookId": {"type": "string"}, "entryId": {"type": "string"}},
                "required": ["worldbookId", "entryId"],
                "additionalProperties": False,
            },
            needs_chat=False,
            needs_memory_write=False,
            needs_destructive=True,
            handler=H["worldbook_entry_delete"],
            scopes=frozenset({GL, WS, CH}),
            risk=ToolRisk.DESTRUCTIVE,
        ),
        _fn(
            "chat_get_worldbook_state",
            "读取本会话的世界书绑定、排除列表等（ChatOverrides）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_get_worldbook_state"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_worldbook_global_exclusion_set",
            "设置本会话是否将某全局世界书排除在注入之外（worldBookGlobalExclusions）。",
            {
                "type": "object",
                "properties": {
                    "worldbookId": {"type": "string"},
                    "excluded": {"type": "boolean"},
                },
                "required": ["worldbookId", "excluded"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_worldbook_global_exclusion_set"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "chat_worldbook_attachment_add",
            "本会话绑定一本世界书（增量）。可选 scanDepth、insertDepth。",
            {
                "type": "object",
                "properties": {
                    "worldbookId": {"type": "string"},
                    "scanDepth": {"type": "integer"},
                    "insertDepth": {"type": "integer"},
                },
                "required": ["worldbookId"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_worldbook_attachment_add"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "chat_worldbook_attachment_remove",
            "移除本会话对某世界书的绑定。",
            {
                "type": "object",
                "properties": {"worldbookId": {"type": "string"}},
                "required": ["worldbookId"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_worldbook_attachment_remove"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "chat_worldbook_attachment_reorder",
            "按 orderedWorldBookIds 顺序重排本会话已绑定的世界书。",
            {
                "type": "object",
                "properties": {"orderedWorldBookIds": {"type": "array", "items": {"type": "string"}}},
                "required": ["orderedWorldBookIds"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_worldbook_attachment_reorder"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "chat_summarize_active_worldbooks",
            "汇总当前会话下会生效的世界书（全局/会话/绑定顺序）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_summarize_active_worldbooks"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "mvu_get_session_state",
            "读取当前会话的 stateVariables 状态快照与提取队列内容（markdown table 格式）。",
            {"type": "object", "properties": {}, "additionalProperties": False},
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["mvu_get_session_state"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "mvu_define_table",
            "定义或替换一张 MVU 状态表。参数：table_name(表名)、columns(列名列表)、fields(行字段名列表，可选)。",
            {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名，唯一标识"},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "列名列表（不含首列 field）"},
                    "fields": {"type": "array", "items": {"type": "string"}, "description": "行字段名列表，用作每行的标识"},
                },
                "required": ["table_name", "columns"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["mvu_define_table"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "mvu_set_cell",
            "设置 MVU 状态表中指定单元格的值。自动创建不存在的列或行。参数：table_name、field、column、value。",
            {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "field": {"type": "string", "description": "行标识（field 列的值）"},
                    "column": {"type": "string", "description": "列名"},
                    "value": {"type": "string", "description": "单元格值"},
                },
                "required": ["table_name", "field", "column", "value"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["mvu_set_cell"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "mvu_get_chat_context",
            "获取当前会话最近 N 条聊天消息（markdown 格式）。参数：count（默认 10，上限 50）。",
            {
                "type": "object",
                "properties": {"count": {"type": "integer", "description": "返回的消息条数，默认 10，上限 50"}},
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["mvu_get_chat_context"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "read_mvu_logs",
            "读取 MVU 助手工作日志（最近 N 条）。参数：limit（默认 50，上限 200）。",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "返回的日志条数，默认 50，上限 200"}},
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["read_mvu_logs"],
            scopes=frozenset({CH}),
            risk=ToolRisk.READ,
        ),
        _fn(
            "chat_content_regex_manage",
            "管理当前会话的正文正则规则（ChatOverrides.contentRegexRules）。"
            "operation=list 列出规则；upsert 传入 rule 对象（更新时含 id）；delete 传入 rule_id。"
            "启用规则会校验 pattern；单会话最多 100 条。",
            {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["list", "upsert", "delete"]},
                    "rule_id": {"type": "string", "description": "delete 时必填"},
                    "rule": {"type": "object", "description": "upsert 时必填，字段同 ChatContentRegexRule"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["chat_content_regex_manage"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "character_content_regex_manage",
            "管理当前会话绑定角色卡（chat.characterId）的正文正则模板（CharacterCard.contentRegexRules）。"
            "群聊仅作用于主角色 characterId。operation=list|upsert|delete，用法同 chat_content_regex_manage。",
            {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["list", "upsert", "delete"]},
                    "rule_id": {"type": "string", "description": "delete 时必填"},
                    "rule": {"type": "object", "description": "upsert 时必填，字段同 ChatContentRegexRule"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["character_content_regex_manage"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
        _fn(
            "patch_state_variable",
            "修补 MVU 状态变量中的指定单元格。仅聊天助手可调用。参数：table_name、field、column、value。",
            {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "field": {"type": "string", "description": "行标识"},
                    "column": {"type": "string", "description": "列名"},
                    "value": {"type": "string", "description": "单元格值"},
                },
                "required": ["table_name", "field", "column", "value"],
                "additionalProperties": False,
            },
            needs_chat=True,
            needs_memory_write=False,
            needs_destructive=False,
            handler=H["patch_state_variable"],
            scopes=frozenset({CH}),
            risk=ToolRisk.WRITE,
        ),
    ]


_REGISTERED: list[RegisteredTool] | None = None


def registered_tools() -> list[RegisteredTool]:
    global _REGISTERED
    if _REGISTERED is None:
        _REGISTERED = _all_registered()
    return _REGISTERED


def build_openai_tools_list(ctx: Any) -> list[dict[str, Any]]:
    from app.assistant_tools.context import AssistantToolContext

    assert isinstance(ctx, AssistantToolContext)
    has_chat = bool(ctx.chat_id)
    out: list[dict[str, Any]] = []
    for rt in registered_tools():
        if rt.needs_chat and not has_chat:
            continue
        if rt.needs_memory_write and not ctx.allow_write_memory:
            continue
        if rt.needs_destructive and not ctx.allow_destructive_tools:
            continue
        out.append(_openai_def(rt))
    return out


HANDLERS_BY_NAME: dict[str, RegisteredTool] | None = None


def tool_entry(name: str) -> RegisteredTool | None:
    global HANDLERS_BY_NAME
    if HANDLERS_BY_NAME is None:
        HANDLERS_BY_NAME = {t.name: t for t in registered_tools()}
    return HANDLERS_BY_NAME.get(name)
