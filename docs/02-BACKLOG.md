# v0.600 Backlog

## P0 已完成

- `T-101-ui-foundation`：统一 surface/card/button/input/modal/drawer/popover/focus/z-index/motion 基座。
- `T-102-chat-main-path`：统一 ChatInput、MessageList、ChatSidebar、AssistantPanel、MvuPanel、TTS 浮层。
- `T-103-settings-panels`：统一 SettingsDrawer、API 预设、TTS、WebGPU、Web Search 常见 surface 与按钮状态。
- `T-104-modal-a11y`：统一导入导出、群聊、消息编辑、知识图谱、HTTP Log、世界书等弹窗外层与关闭按钮无障碍。
- `T-105-backend-fast-fail`：MVU/知识图谱路由集中会话 fast-fail，错误详情结构化。
- `T-106-tests-docs-version`：补 UI primitive、dialog focus、MVU route 错误测试，更新 README/CHANGELOG/state/version。

## P1 后续强化

- 将 `SettingsDrawer.vue` 拆分为 API 预设、TTS、WebGPU、Web Search、会话覆盖等子组件。
- 将 `ChatPage.vue` 拆分为角色/身份编辑、导入导出、生成流和会话管理子模块。
- 为 modal/drawer 建立组件测试或轻量 Vue 测试基座。
- 将剩余低频 modal 全量接入 `dialogAria` / `useDialogBehavior`，包括导入导出、HTTP Log、WebGPU、世界书与 ChatPage 内联弹层。
- 扩展数据完整性扫描到损坏角色、世界书和设置。
- 为 import/export 增加更多 warning 汇总。

## P2 推迟

- 原生 Responses / Anthropic / Gemini 协议层。
- Playwright E2E。
- 后端全局 chatId 索引迁移。

## 当前顺序

1. `T-101-ui-foundation`
2. `T-102-chat-main-path`
3. `T-103-settings-panels`
4. `T-104-modal-a11y`
5. `T-105-backend-fast-fail`
6. `T-106-tests-docs-version`
7. `T-107-final-verify`
