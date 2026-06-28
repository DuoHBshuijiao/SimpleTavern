# v0.500 Backlog

## P0 必做

- `T-001-docs-task-base`：建立文档接力骨架和 v0.500 发布任务入口。
- `T-002-test-baseline`：新增后端 pytest 和前端正文正则 golden 测试。
- `T-003-frontend-p0`：修复前端设置丢失、叠层、Esc/确认框、正文正则显示和 MessageList 缓存。
- `T-004-backend-p0`：修复后端 preset 解析、scanner/MVU 队列、无效角色会话和导入警告。

## P1 强烈建议

- `T-005-release-docs`：更新 README、CHANGELOG 与 v0.500 发布清单。
- 为 modal 增加 `role="dialog"`、`aria-modal`、关闭按钮 `aria-label` 和焦点管理。
- 扩展数据完整性扫描到损坏角色、世界书和设置。
- 为 import/export 增加更多 warning 汇总。

## P2 推迟

- 全量样式令牌收束。
- `ChatPage.vue` 与 `SettingsDrawer.vue` 大拆分。
- 原生 Responses / Anthropic / Gemini 协议层。
- 组件测试与 E2E。

## 当前顺序

1. `T-001-docs-task-base`
2. `T-002-test-baseline`
3. `T-003-frontend-p0`
4. `T-004-backend-p0`
5. `T-005-release-docs`
6. `T-006-final-verify`
