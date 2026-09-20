# T-807 v0.800 消息 generation metadata + usage ledger

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**（消息 metadata + append-only ledger；定价引擎/统计 API 归 T-808）
- area: backend `routes/generate.py` + `services/usage_ledger.py` + `ChatMessage`
- priority: P0
- theme: 云端 usage 原样保留并归一化；账本幂等；写失败可见
- depends_on: T-804（完成）、T-806-6C（本批一并落地）

## 目标

每次主聊天生成（单聊 / 群聊 / 插话）在助手消息上写入 `generationMetadata`，并向 `data/usage/YYYY-MM.jsonl` 追加一条事件。不扫描全部 chat JSON 也能做后续统计（T-808）。

## 完成定义

- `ChatMessage.generationMetadata` 可选、versioned；旧消息可加载。
- 归一化 usage 与 SSE/`ChatMessage.usage` 同源（camelCase）；供应商未返回 cost 时 `cost.source=unknown`，不得填 0。
- ledger `eventId = requestId:messageId:status` 幂等；重复写入跳过。
- 账本写失败：`usage_persist_failed`，并尽量写入 `data/usage/repair.jsonl`。消息若已保存，不把该轮 SSE `done` 伪装成完整成功。
- 不含 API Key、完整请求体、敏感 header。
- 不实现 GET `/api/usage/*` 与设置页仪表盘（T-808）。

## 路径

- `backend/app/services/usage_ledger.py`
- `backend/app/routes/generate.py`（stream / group / interject）
- `data/usage/YYYY-MM.jsonl`、`data/usage/usage_index.json`
