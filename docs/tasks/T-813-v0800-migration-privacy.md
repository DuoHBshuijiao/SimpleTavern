# T-813 v0.800 迁移、隐私与向后兼容

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**
- area: settings 迁移警告、usage ledger 脱敏、旧 JSON extra=allow
- priority: P1
- theme: 旧数据可加载；密钥不进账本；迁移必须写 warning
- depends_on: T-807、T-808

## 目标

结构迁移可见、不可静默修复损坏配置；账本与 repair 队列不含密钥或完整请求体。

## 完成定义

- `ChatMessage` 等模型 `extra="allow"`，新增字段可选；旧会话 JSON 可 `load_chat`。
- 旧设置缺 `worldBookEntryScanDepthDefault`、API 预设缺 `protocol`：读取时写入 `data/migration_warnings.jsonl`（文案打码），协议默认 `openai_compatible_chat` 但不宣称配置已探测有效。
- ledger 事件 allowlist + `redact_sensitive_text`；repair.jsonl 同样脱敏。
- `GET /api/health.migrationWarnings`：count + 最近 5 条。

## 路径

- `backend/app/services/migration_log.py`
- `backend/app/storage.py`（`load_settings`）
- `backend/app/services/usage_ledger.py`（`_sanitize_event`）
- `backend/app/main.py`（health）
