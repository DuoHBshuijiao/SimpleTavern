# Last Handoff

- last_task: `T-802-batch-2-storage-chat-fork`
- status: completed（T-802 overall in-progress）
- summary: 完成 Storage/chat/fork 损坏数据可见化、fork 索引自愈与 cleanup-only 可观测性。
- code_changes:
  - 角色/世界书列表保持数组契约；损坏项实时写入既有 data-integrity issue，避免破坏前端 stores。
  - 损坏角色、世界书、会话直接加载统一 `data_corrupted`；真实缺失仍为 not-found。
  - runtime chat issue 保持完整校验直到磁盘文件修复；读取错误禁止自动删除。
  - `update_ignore.json` 损坏统一 `update_ignore_corrupt`，不再覆写原文件。
  - fork index 损坏从 chat 元数据重建并返回 warnings；失败为 retryable error；sync 失败标 dirty 并在下次 lineage 重建。
  - cleanup-only 统一 `cleanup_failed` 结构化日志与 requestId，目录仍逐项尽力清理。
  - 前端 fork warning/error 接入现有错误栈。
- review_fixes:
  - 修复 runtime chat issue 首次轮询后降级为轻量校验导致的误清。
  - `read_error` 改为人工处理，防止瞬时 I/O 错误触发删除建议。
  - 恢复 `rmtree` 逐项尽力清理，不因首个失败扩大残留。
  - fork sync 失败增加 dirty 标记；不可读 meta warning 持久保留。
  - 启动更新检查不再把 `update_ignore_corrupt` 包成泛 502。
  - 瞬时不可稳定读取改为独立扫描状态，不再误清尚未修复的 integrity issue。
  - fork corrupt/sync warning 在成功重建时写入索引，后续 lineage API 持续可见。
- known_gap:
  - generate 落库前未调用 `apply_content_regex_pipeline`，与工作区文档契约不一致；已登记 F-010，本批未改变持久化语义。
  - F-009 世界书坏 regex 仍待用户可见 warning。
- verification:
  - Bugbot 修复 focused contracts → 24 passed。
  - fork index 1000 chats / 99 forks cold rebuild → `410.05 ms`（门槛 `< 5000 ms`）。
  - `cd backend && python -m pytest tests/ -q` → 169 passed。
  - `cd frontend && npm run test` → 123 passed。
  - `cd frontend && npm run build` → passed。
- version_note: `backend/app/version.py` 仍为 `v0.700`；待 v0.800 发布门禁完成后再改。
- next_read:
  1. `docs/tasks/T-802-v0800-backend-fallback-audit.md`
  2. `docs/audits/v0800-backend-fallback-inventory.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-802 第三批迁移 Assistant/tools（F-017~F-020）；F-010 正文正则需先确认唯一产品语义。不要同时开始 T-804 协议内核或计量大改。
