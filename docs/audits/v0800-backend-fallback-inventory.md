# v0.800 Backend Fallback Inventory

- task: `T-802`
- status: in-progress
- generated: `2026-07-10`
- schema: `id | domain | file | symbol | current_behavior | classification | target_code | user_surface | test | status`
- classifications: `fatal | partial | retryable | explicit-fallback | cleanup-only | verify-first`
- note: `current_behavior` 记录迁移前基线；`status=done` 表示该行为已被目标契约替换。

## Coverage

| Domain | Inventory | Migration |
|---|---|---|
| LLM / generate | complete for P0/P1 scan | batch 1 complete |
| storage / chats / fork | initial high-risk scan complete | pending |
| assistant / tools | initial high-risk scan complete | pending |
| MVU / KG / regex | initial high-risk scan complete | pending |
| search | initial high-risk scan complete | pending |
| import / export / avatar | initial high-risk scan complete | pending |
| TTS | initial high-risk scan complete | pending |
| infra / background | initial high-risk scan complete | pending |

## Inventory

| id | domain | file | symbol | current_behavior | classification | target_code | user_surface | test | status |
|---|---|---|---|---|---|---|---|---|---|
| F-001 | llm | `backend/app/llm/openai_compat.py` | `stream_chat_completions` | 非法/未知 SSE 帧被跳过 | fatal | `stream_event_invalid` | terminal SSE error | `test_openai_compat.py` | done |
| F-002 | llm | `backend/app/llm/openai_compat.py` | `chat_completions*` | 空 choices 返回空正文/空消息 | fatal | `provider_response_invalid` | REST/SSE envelope | `test_openai_compat.py` | done |
| F-003 | llm | `backend/app/llm/openai_compat.py` | `stream_chat_completions` | 无输出/无结束标记仍产出 finish | fatal | `provider_response_invalid` / `stream_interrupted` | terminal SSE error | `test_openai_compat.py` | done |
| F-004 | llm | `backend/app/routes/llm.py` | `get_models` / `test_models` | 上游空列表静默替换本地候选，或返回 200 + `[]` | fatal | `model_list_empty` | REST error + requestId | `test_error_contract.py` | done |
| F-005 | generate | `backend/app/routes/generate.py` | draft/group/interject event iterators | SSE 失败仅返回裸 message | fatal | `generation_failed` | terminal SSE error | `test_generate_error_contracts.py` | done |
| F-006 | generate | `backend/app/routes/generate.py` | draft/group/interject nonstream | 500 返回旧 `{ok,error}` | fatal | `generation_failed` | REST envelope | `test_generate_error_contracts.py` | done |
| F-007 | generate | `backend/app/routes/generate.py` | group/interject web search preflight | 开启但未配置时静默关闭工具 | fatal | `web_search_not_configured` | REST error before generation | `test_generate_error_contracts.py` | done |
| F-008 | generate | `backend/app/services/generate_web_search_runtime.py` | tool argument parsing | 非法 JSON 退化为 `{}` 并继续调用 | fatal | `tool_call_invalid` | terminal generation error | `test_generate_web_search_runtime.py` | done |
| F-009 | generate | `backend/app/routes/generate.py` | `match_worldbook_entries` | 坏 regex 被跳过 | partial | `worldbook_regex_invalid` | warnings/error stack | pending | open |
| F-010 | regex | generate save paths | assistant persistence | 未调用正文正则管线；与工作区契约不一致 | verify-first | pending decision | pending decision | fact regression | verified-gap |
| F-011 | storage | `backend/app/storage.py` | `list_characters` | 损坏 JSON `continue`，角色从列表消失 | partial | `character_corrupt` | `corruptEntries[]` | pending | open |
| F-012 | storage | `backend/app/storage.py` | `list_worldbooks` | 损坏 JSON `continue`，世界书从列表消失 | partial | `worldbook_corrupt` | `corruptEntries[]` | pending | open |
| F-013 | storage | `backend/app/storage.py` | `_load_chat_from_path` | 读取异常返回 `None` | partial | `chat_corrupt` | integrity issue | pending | open |
| F-014 | storage | `backend/app/storage.py` | `load_update_ignore` | 损坏配置重置为空对象 | partial | `update_ignore_reset` | warning/health | pending | open |
| F-015 | fork | `backend/app/fork_index.py` | `_load_index_unlocked` | 损坏索引静默重置为空 | partial | `fork_index_corrupt` | rebuild warning | pending | open |
| F-016 | storage | `backend/app/storage.py` | delete/clear cleanup | 清理失败 `pass` / `continue` | cleanup-only | `cleanup_failed` | structured log | pending | open |
| F-017 | assistant | `backend/app/routes/assistant.py` | `_normalize_assistant_chat_for_save` | 校验失败仍保存原对象 | fatal | `assistant_message_invalid` | REST error | pending | open |
| F-018 | assistant | `backend/app/services/assistant_agent.py` | tool argument parsing | 非法 JSON 退化为 `{}` | fatal | `tool_call_invalid` | ToolResult + error stack | pending | open |
| F-019 | assistant | `backend/app/services/assistant_agent.py` | stream/nonstream errors | 仅传 `str(exc)` | fatal | mapped AppError | REST/SSE envelope | pending | open |
| F-020 | assistant | assistant workspace card route | workspace failure | HTTP 200 + `{ok:false}` | fatal | `data_not_found` / `data_corrupted` | REST error | pending | open |
| F-021 | mvu | `backend/app/services/mvu_daemon.py` | worker loop | 失败日志后无限继续，无 health | retryable | `mvu_worker_failed` | health/lastError | pending | open |
| F-022 | mvu | `backend/app/services/mvu_daemon.py` | `_broadcast` | QueueFull 静默丢事件 | partial | `mvu_sse_dropped` | dropped counter | pending | open |
| F-023 | mvu | `backend/app/group_mvu.py` | runtime enable check | 角色读取失败被视为功能关闭 | fatal | `mvu_character_unreadable` | explicit error state | pending | open |
| F-024 | mvu | `backend/app/services/mvu_agent.py` | tool argument parsing | 非法 JSON 退化为 `{}` | fatal | `tool_call_invalid` | worker error state | pending | open |
| F-025 | regex | `backend/app/content_regex_scanner.py` | scanner loop | 失败仅日志/退避，无 health | retryable | `content_regex_scanner_failed` | health/lastError | pending | open |
| F-026 | regex | `backend/app/content_regex_queue.py` | enqueue | 队列超限静默丢最旧项 | partial | `content_regex_queue_dropped` | dropped counter | pending | open |
| F-027 | search | `backend/app/services/web_search.py` | async/sync search | provider 失败变 JSON 字符串工具结果 | partial | provider-specific search error | ToolResult + error stack | pending | open |
| F-028 | import/export | `backend/app/routes/import_export.py` | character export | 缺失 worldbook 被跳过 | partial | `export_attachment_missing` | warnings/manifest | pending | open |
| F-029 | import/export | import row/candidate loops | item failure | 已有 warning，但结构不统一 | partial | domain-specific warning | `partialSuccess/warnings[]` | pending | open |
| F-030 | TTS | GLM local synthesize | endpoint selection | JSON 失败自动改 multipart | explicit-fallback | `tts_endpoint_fallback` | from/to/reason | pending | open |
| F-031 | TTS | SiliconFlow voice list | remote list | 失败后仅返回内置预设 | partial | `tts_voice_list_partial` | partial warning | pending | open |
| F-032 | TTS | local process health/cleanup | process errors | 异常退化为 False/pass | cleanup-only | process health codes | health API | pending | open |
| F-033 | infra | `backend/app/services/http_log.py` | record write | 序列化/写盘失败可能丢记录 | cleanup-only | `http_log_write_failed` | health counter | pending | open |
| F-034 | infra | `backend/app/tokenizer_service.py` | tokenizer load | 不可用返回 None | explicit-fallback | `tokenizer_unavailable` | unavailable, not zero | pending | open |

## Already migrated by T-801

| id | behavior | status |
|---|---|---|
| M-001 | `list_models_openai_compat` 失败抛 AppError | done |
| M-002 | `/llm/test-models` 不再返回 200 + `[]` | done |
| M-003 | `/generate/stream` 使用 meta + terminal error + success-only done | done |
| M-004 | 主生成网络搜索未配置时在写入用户消息前 fast-fail | done |

## Explicit non-errors

- 生命周期 `CancelledError`、取消任务后的 `pass`：cleanup-only。
- 已保留主异常的 rollback 清理失败：cleanup-only，后续只补结构化日志。
- 正文正则单规则错误进入 `errors[]` 并继续：partial，不应改为全批 fatal。
- 导入逐项失败且已进入 warnings：partial，后续统一结构，不机械改 fatal。
- `character.name or "角色"`、`user_name or "用户"`：展示默认值。
- SSE 空行、`data: [DONE]` 和明确 `:` comment/keepalive：协议允许。
- clipboard/平台能力探测失败：显式能力降级。
