# Backlog

## v0.700 任务（已完成）

- [x] T-201 ~ T-208（测试基座、3 composable、数据完整性、import warning、UI 首批）
- [x] T-209 UI/动画全面收束
- [x] T-210 ChatPage composable 第二批
- [x] T-211 SettingsDrawer 渐进拆分
- [x] T-212 ChatPage 弹层/composable 拆分（SSE 主体 → v0.800）
- [x] T-213 ChatInput 动效与 motion audit
- [x] T-214 可观测性前端收尾 + 版本文档收口

## v0.800 任务（下一版）

- [ ] **T-800** 总卡：见 `docs/tasks/T-800-v0800-backend-performance.md`
- [ ] T-801 ChatPage SSE / `useChatGeneration` composable
- [ ] T-802~803 后端索引与生成/MVU 热路径
- [ ] T-804 完整性 orphan 扩展 + 导出 warnings API
- [ ] T-805 全链路验证

### v0.800 合并推进（与 T-801 同批）

- SSE composable 与后端生成路径共用边界，避免 v0.700 前后端重复改接口
- 数据完整性 worldbook orphan、导出跳过项需后端 API

## v0.900+

- 原生 Responses / Anthropic / Gemini 多厂商对话协议层
- Playwright E2E

## v0.600 Backlog

## P0 已完成

- `T-101-ui-foundation`：统一 surface/card/button/input/modal/drawer/popover/focus/z-index/motion 基座。
- `T-102-chat-main-path`：统一 ChatInput、MessageList、ChatSidebar、AssistantPanel、MvuPanel、TTS 浮层。
- `T-103-settings-panels`：统一 SettingsDrawer、API 预设、TTS、WebGPU、Web Search 常见 surface 与按钮状态。
- `T-104-modal-a11y`：统一导入导出、群聊、消息编辑、知识图谱、HTTP Log、世界书等弹窗外层与关闭按钮无障碍。
- `T-105-backend-fast-fail`：MVU/知识图谱路由集中会话 fast-fail，错误详情结构化。
- `T-106-tests-docs-version`：补 UI primitive、dialog focus、MVU route 错误测试，更新 README/CHANGELOG/state/version。

## P1 后续强化

- 将 `SettingsDrawer.vue` 拆分为 API 预设、TTS、WebGPU、Web Search、会话覆盖等子组件。→ **v0.700 已完成 Tab 级拆分**
- 将 `ChatPage.vue` 拆分为角色/身份编辑、导入导出、生成流和会话管理子模块。→ **弹层已完成；生成流 v0.800**
- 为 modal/drawer 建立组件测试或轻量 Vue 测试基座。→ **v0.700 已建**
- 扩展数据完整性扫描到损坏角色、世界书和设置。→ **v0.700 已完成；worldbook orphan v0.800**
- 为 import/export 增加更多 warning 汇总。→ **导入 v0.700；导出 API v0.800**

## P2 推迟

- 原生 Responses / Anthropic / Gemini 协议层。→ **v0.900+**
- Playwright E2E。
- 后端全局 chatId 索引迁移。→ **v0.800**
