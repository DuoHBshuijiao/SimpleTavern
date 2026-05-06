"""Assistant tool handlers by domain."""

from __future__ import annotations

from typing import Any, Callable

from app.assistant_tools.handlers import chat, content_regex_tools, core, mvu, workspace, worldbook

HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "core_get_time": core.handle_core_get_time,
    "workspace_read_file": workspace.handle_workspace_read_file,
    "workspace_create_file": workspace.handle_workspace_create_file,
    "workspace_write_file": workspace.handle_workspace_write_file,
    "workspace_delete_file": workspace.handle_workspace_delete_file,
    "workspace_patch_character_card": workspace.handle_workspace_patch_character_card,
    "workspace_replace_character_card": workspace.handle_workspace_replace_character_card,
    "chat_read_conversation": chat.handle_chat_read_conversation,
    "chat_read_long_term_memory": chat.handle_chat_read_long_term_memory,
    "chat_read_character_card": chat.handle_chat_read_character_card,
    "chat_list_participants": chat.handle_chat_list_participants,
    "chat_append_long_term_memory": chat.handle_chat_append_long_term_memory,
    "chat_overwrite_long_term_memory": chat.handle_chat_overwrite_long_term_memory,
    "worldbook_list": worldbook.handle_worldbook_list,
    "worldbook_get": worldbook.handle_worldbook_get,
    "worldbook_create": worldbook.handle_worldbook_create,
    "worldbook_update_meta": worldbook.handle_worldbook_update_meta,
    "worldbook_delete": worldbook.handle_worldbook_delete,
    "worldbook_entry_add": worldbook.handle_worldbook_entry_add,
    "worldbook_entry_update": worldbook.handle_worldbook_entry_update,
    "worldbook_entry_delete": worldbook.handle_worldbook_entry_delete,
    "chat_get_worldbook_state": chat.handle_chat_get_worldbook_state,
    "chat_worldbook_global_exclusion_set": chat.handle_chat_worldbook_global_exclusion_set,
    "chat_worldbook_attachment_add": chat.handle_chat_worldbook_attachment_add,
    "chat_worldbook_attachment_remove": chat.handle_chat_worldbook_attachment_remove,
    "chat_worldbook_attachment_reorder": chat.handle_chat_worldbook_attachment_reorder,
    "chat_summarize_active_worldbooks": chat.handle_chat_summarize_active_worldbooks,
    "mvu_get_session_state": mvu.handle_mvu_get_session_state,
    "mvu_define_table": mvu.handle_mvu_define_table,
    "mvu_set_cell": mvu.handle_mvu_set_cell,
    "mvu_get_chat_context": mvu.handle_mvu_get_chat_context,
    "read_mvu_logs": chat.handle_chat_read_mvu_logs,
    "patch_state_variable": chat.handle_chat_patch_state_variable,
    "chat_content_regex_manage": content_regex_tools.handle_chat_content_regex_manage,
    "character_content_regex_manage": content_regex_tools.handle_character_content_regex_manage,
}

__all__ = ["HANDLERS"]
