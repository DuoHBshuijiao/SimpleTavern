# Last Handoff

- last_task: `T-802-batch-3-assistant-tools`
- status: completed（T-802 overall in-progress）
- summary: 完成 Assistant/tools 静默 fallback 迁移（F-017~F-020）：脏消息禁写、工具参数 fast-fail、Agent 错误 envelope、workspace 角色卡 REST 契约。
- code_changes:
  - `_normalize_assistant_chat_for_save` 校验失败抛 `assistant_message_invalid`，禁止脏对象落盘。
  - agent 工具参数非法 JSON/非对象返回 `tool_call_invalid` ToolResult，不再以 `{}` 调用工具。
  - executor 对非 dict args 返回 VALIDATION_ERROR（kind=tool_call_invalid）。
  - agent 非流异常改为抛 AppError；流式 error 事件带完整 ErrorEnvelope + terminal。
  - `/assistant/stream` 增加 requestId/meta/done，非流失败走 `app_error_response`。
  - GET workspace character-card：缺失 `data_not_found`、损坏 `data_corrupted`、成功返回 CharacterCard。
  - 前端 `openCreateCharacter` 按 CharacterCard 响应读取，404/500 仍进 catch 当作无草稿。
- known_gap:
  - F-009 世界书坏 regex 仍待用户可见 warning。
  - F-010 已关闭（语义 A）。
- verification:
  - `cd backend && python -m pytest tests/ -q` → 178 passed。
  - 本机 `frontend/node_modules` 缺失，未跑前端 test/build；改动为单点 API 契约适配。
- version_note: `backend/app/version.py` 仍为 `v0.700`；待 v0.800 发布门禁完成后再改。
- next_read:
  1. `docs/tasks/T-802-v0800-backend-fallback-audit.md`
  2. `docs/audits/v0800-backend-fallback-inventory.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-802 第四批迁移 MVU/KG/regex scanner（F-021~F-026）；可选穿插 F-009。不要同时开始 T-804 协议内核或计量大改。
