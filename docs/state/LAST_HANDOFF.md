# Last Handoff

- last_task: `T-802-batch-5-search-import-export`
- status: completed（T-802 overall in-progress）
- summary: 完成 Search provider 失败契约（F-027）与 Import/Export warning 统一（F-028~F-029）。
- code_changes:
  - F-027：`run_web_search` / `run_web_search_sync` 返回 `{ok, code, message, result?}`；助手工具失败走 `ToolResult.err`；generate runtime 用 `format_web_search_tool_content`。
  - F-028：角色导出 ZIP `manifest.json` 含 `warnings` / `partialSuccess` / `exportedWorldBookIds`（含 `export_attachment_missing`）。
  - F-029：导入 warning 统一 `_import_warning` 结构；前端 `ImportWarningItem` + `coerceImportWarningText` 兼容 string/dict。
  - 静默 fallback 守卫纳入 `web_search.py` / `import_export.py` / web_search handler。
- known_gap:
  - 前端尚未消费 MVU/regex health/dropped UI（后端 API 已就绪）。
  - TTS / infra（F-030~F-034）仍待迁移。
- verification:
  - `cd backend && python -m pytest tests/ -q` → 191 passed。
- version_note: `backend/app/version.py` 仍为 `v0.700`；待 v0.800 发布门禁完成后再改。
- next_read:
  1. `docs/tasks/T-802-v0800-backend-fallback-audit.md`
  2. `docs/audits/v0800-backend-fallback-inventory.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-802 第六批 TTS / infra（F-030~F-034）。不要同时开始 T-804 协议内核或计量大改。
