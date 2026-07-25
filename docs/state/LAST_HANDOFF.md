# Last Handoff

- last_task: `T-802-batch-4-mvu-regex-health`
- status: completed（T-802 overall in-progress）
- summary: 完成 MVU/KG/regex scanner health 与 dropped 计数（F-021~F-026），并顺带关闭 F-009 世界书坏 regex warning。
- code_changes:
  - 新增 `worker_health.WorkerHealth`；MVU worker / content-regex scanner 维护 failureCount/lastError/paused/nextRetryAt。
  - F-021：MVU loop 失败写 health + SSE error envelope，连续失败暂停并半开重试。
  - F-022：QueueFull 计数 `sseDropped` 并打 warning 日志。
  - F-023：`resolve_chat_mvu_runtime_enablement` 区分未开启与 `mvu_character_unreadable`；KG 门控透传 code。
  - F-024：MVU agent 复用工具参数解析，非法 JSON → `tool_call_invalid` ToolResult。
  - F-025/F-026：scanner health + 队列超限 `dropped` 计数；暴露 `GET /api/mvu/{chatId}/health` 与 `GET /api/content-regex/health`。
  - F-009：坏世界书 regex 收集 `worldbook_regex_invalid` warning 并写入 generate SSE meta。
- known_gap:
  - 前端尚未消费 health/dropped UI（后端 API 已就绪）。
  - Search / import-export / TTS / infra（F-027~F-034）仍待迁移。
- verification:
  - `cd backend && python -m pytest tests/ -q` → 185 passed。
- version_note: `backend/app/version.py` 仍为 `v0.700`；待 v0.800 发布门禁完成后再改。
- next_read:
  1. `docs/tasks/T-802-v0800-backend-fallback-audit.md`
  2. `docs/audits/v0800-backend-fallback-inventory.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-802 第五批 Search（F-027）或 import/export/avatar（F-028~F-029）。不要同时开始 T-804 协议内核或计量大改。
