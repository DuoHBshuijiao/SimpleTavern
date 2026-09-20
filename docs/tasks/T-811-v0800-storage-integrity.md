# T-811 v0.800 Storage / Integrity / 锁超时可见

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**
- area: storage、data_integrity、import/export 警告
- priority: P1
- theme: orphan、跳过项、锁冲突均可感知
- depends_on: T-801、T-803

## 目标

世界书孤儿引用进入完整性扫描；文件锁等待超时变成结构化错误；导出跳过项继续以 warning 返回。

## 完成定义

- 扫描 chat `overrides.worldBookIds` / `worldBookAttachments`：缺失世界书 → `orphan_worldbook`，`repairAction=none`（需人工处理）。
- 前端完整性文案：「世界书缺失」。
- portalocker 非阻塞轮询，超时 30s → `file_lock_timeout` HTTP 503，`retryable=true`；health `locks.timeoutCount` / `lastTimeoutAt` / `timeoutSec`。
- 导出 ZIP 已有 `warnings[]` + `partialSuccess`（既有 import_export 路径，本卡核对其可见）。

## 路径

- `backend/app/storage.py`（`_acquire_portalock`、`get_lock_observability`）
- `backend/app/services/data_integrity.py`
- `frontend/src/api/dataIntegrity.ts`、`frontend/src/utils/dataIntegrityNotify.ts`
