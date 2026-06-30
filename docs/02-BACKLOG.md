# Backlog

## v0.700 任务（已完成）

- [x] `T-201-component-test-base`：引入 `@vue/test-utils` + `happy-dom`，新增可挂载 SFC 的组件测试与 `ThemedCheckbox` 示例。
- [x] `T-202-use-chat-search`：从 `ChatPage.vue` 提炼 `useChatSearch`（会话内搜索状态机）+ 单测。
- [x] `T-203-use-image-sticky`：从 `ChatPage.vue` 提炼 `useImageStickyBinding`（图片粘性绑定/回退）+ 单测。
- [x] `T-204-use-fork-lineage`：从 `ChatPage.vue` 提炼 `useForkLineage`（分叉血缘）+ 单测。
- [x] `T-205-data-integrity-expand`：后端数据完整性扫描扩展到 settings/characters/worldbooks + characterId orphan 引用（仅检测），补测试与前端区分展示。
- [x] `T-206-import-export-warnings`：修复 MVU 兼容 warning 互斥丢失、TXT(V2) 导入 warning 透传，补前后端测试。
- [x] `T-207-v0700-final-verify`：全套验证 + 文档/版本/state/changelog 更新。
- [x] `T-208-ui-ux-impeccable`：Impeccable 批次——顶栏圆角 token、ChatSidebar 选中态、图片回退弹层、搜索 a11y、完整性巡检文案。

### v0.700 推迟（→ v0.800+）

- ChatPage 生成/SSE orchestration 拆分、SettingsDrawer 大拆。
- 更多 orphan 类型（attachedWorldBookIds 悬空）、导出跳过项告知、更多导入路径 warning 透传。
- 原生 Responses / Anthropic / Gemini 协议层、Playwright E2E、后端全局 chatId 索引迁移。

## v0.600 Backlog

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
