# Backlog

## v0.700 任务

### 已完成

- [x] T-201 ~ T-208（测试基座、3 composable、数据完整性、import warning、UI 首批）

### 进行中

- [x] **T-209** UI/动画全面收束（Impeccable chat/modals/SettingsDrawer；ChatInput margin 另开 T-213）
- [x] **T-210** ChatPage composable 第二批（含顶栏布局/FAB）
- [ ] **T-211** SettingsDrawer 渐进拆分（Teleport 三弹层已完成；accordion/Tab 待做）
- [ ] **T-212** ChatPage 子模块拆分（角色编辑、导入导出壳层）
- [ ] **T-213** ChatInput 动效与全站 motion audit
- [ ] **T-214** 可观测性剩余项 + v0.700 收尾验证

### v0.700 顺序

T-209 → T-210 → T-211 → T-212 → T-213 → T-214

### 推迟到 v0.800（后端性能）

- chatId 全局索引、后端扫描/加载路径优化、生成/MVU 热路径 profiling
- **不再**承担 SettingsDrawer/ChatPage 大拆与 UI 全面扫尾

### 推迟到 v0.900+

- 原生 Responses / Anthropic / Gemini 协议层、Playwright E2E

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
