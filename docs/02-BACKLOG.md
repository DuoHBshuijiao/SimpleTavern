# Backlog

## v0.700 任务（已完成）

- [x] T-201 ~ T-208（测试基座、3 composable、数据完整性、import warning、UI 首批）
- [x] T-209 UI/动画全面收束
- [x] T-210 ChatPage composable 第二批
- [x] T-211 SettingsDrawer 渐进拆分
- [x] T-212 ChatPage 弹层/composable 拆分（SSE 主体 → v0.800）
- [x] T-213 ChatInput 动效与 motion audit
- [x] T-214 可观测性前端收尾 + 版本文档收口
- [x] T-215 Impeccable 前端设计审计与 token/motion 收口

## v0.800 任务（当前版本）

- [ ] **T-800** 后端可信执行层总卡（规划已建立）
- [x] **T-801 P0** Fast-Fail 错误基座：统一 REST/SSE envelope、requestId、前端错误栈
- [ ] **T-802 P0** 全 backend 静默 fallback/catch 审计与迁移（前四批 LLM/generate、Storage、Assistant、MVU/regex 已完成；含 F-009）
- [ ] **T-803 P0** 性能基线、profiling、共享 HTTP client、索引/锁/原子写
- [ ] **T-804 P0** LLM 协议内核与 OpenAI-compatible 迁移
- [ ] **T-805 P0** OpenAI Responses / Anthropic Messages / Gemini 原生协议
- [ ] **T-806 P0** 多套工具调用/消息维护/流事件 + Anthropic 显式缓存开关
- [ ] **T-807 P0** 消息 generation metadata + append-only usage ledger
- [ ] **T-808 P1** 本地定价引擎 + 会话/全局/按模型统计 API 与设置页 UI
- [ ] **T-809 P1** 网络搜索供应商与 provider-native grounding 扩展
- [ ] **T-810 P1** Generate/Assistant/MVU/KG/Regex/TTS 性能与健壮性
- [ ] **T-811 P1** Storage/Chats/Fork/Import/Export/Integrity 性能与错误收口
- [ ] **T-812 P1** ChatPage SSE → `useChatGeneration`，统一 meta/usage/done/error
- [ ] **T-813 P1** 数据迁移、隐私、安全与向后兼容
- [ ] **T-814 P0** 全链路验证、性能门禁、错误审计与发布

### 执行顺序

```text
T-801 错误基座
  ├─ T-802 全后端迁移
  ├─ T-803 性能基础设施
  └─ T-804 协议内核
       ├─ T-805 原生协议
       │    └─ T-806 工具/消息/缓存
       └─ T-807 计量账本
            └─ T-808 成本统计

T-809 / T-810 / T-811 在基座完成后并行
T-812 等错误与 usage SSE 契约稳定后推进
T-813 → T-814 收尾
```

### 强制覆盖

- “全 backend”不是只改 `routes/generate.py`：LLM、storage、chats、fork、assistant/tools、MVU、KG、regex、TTS、search、import/export、integrity、HTTP log、update、avatar、clipboard、daemon/sweeper 都需登记。
- 每个捕获异常点必须选择：向上抛、转换为 AppError、显式 warning、用户配置的 fallback；不得留无说明的 `pass` / `return None` / `[]`。
- 每项性能优化必须有基线、改后数据与回归门槛。
- 协议字段实现前查官方文档并保存 fixture，不凭兼容层经验猜字段。

## v0.900+

- Playwright E2E
- provider 插件 SDK、跨设备/远端统计同步等非核心扩展

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

- 原生 Responses / Anthropic / Gemini 协议层。→ 原计划 v0.900+，现已调整为 **v0.800 T-805/T-806**
- Playwright E2E。
- 后端全局 chatId 索引迁移。→ **v0.800**
