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
- [x] **T-802 P0** 全 backend 静默 fallback/catch 审计与迁移（F-001~F-034 六批完成）
- [x] **T-803 P0** 性能基线、profiling、共享 HTTP client、索引/锁/原子写（3A–3D 完成）
- [x] **T-804 P0** LLM 协议内核与 OpenAI-compatible 迁移
- [x] **T-805 P0** OpenAI Responses / Anthropic Messages / Gemini 原生协议（5A–5D ✅）
- [ ] **T-806 P0** 工具 round-trip / 消息维护 / 流事件 + Anthropic cache（off/5m/1h）+ Responses 高级能力
  - [x] 6A Anthropic cache `off|5m|1h`
  - [x] 6B 多协议工具 round-trip
  - [ ] 6C Responses 内建 web_search（Gemini CachedContents 已并入 v0.810 T-821）
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

## v0.810 任务（当前版本，插在 T-806-6B 之后）

- [x] **T-820 P0** 供应商目录扩充与特殊鉴权支持（信源：pi providers）
  - [x] A1 `sync_llm_catalog.py` + `providers/models generated JSON` + overlay + `catalog.py` + `GET /api/llm/catalog`；combobox 分组/搜索/徽标，选择联动 protocol/authStyle/providerParams
  - [x] A2 AuthStyle/URL 模板泛化：Azure Responses、Vertex Express、Bedrock Anthropic 变体；Cloudflare/Vercel/OpenCode 等目录条目
  - [x] A3 GitHub Copilot 设备码 / OpenAI Codex PKCE 登录 → **v0.820 T-830**
- [x] **T-821 P0** 分协议显式缓存策略 + 教学弹窗
  - [x] B1 `promptCache` 字段与迁移、四协议缓存写法、Usage 归一化、Chat 流式 usage 帧、Gemini cachedContents 404 重建
  - [x] B2 预设编辑器/全局连接区「缓存策略」区块 + 消息 usage 缓存徽标
  - [x] B3 `PromptCacheGuideModal` 近全屏教学弹窗
- [x] **T-822 P0** 模型自适应协议与参数翻译：`resolution.py`、`auto` 协议、effort clamp 含 `max`、`resolve-preview`
- [x] **T-824 P0** 聊天栏「模型控制面板」：会话级 `reasoningEffort/fastMode`，四协议 `none` 关思考与 Fast 写法
- [x] **T-823 P1** 文档、验证与发布收口（`version.py` 已为 `v0.810`；真实 key 探测已搁置）

### 依赖

```text
T-820-A1 目录数据 ─┬─ T-822 后端解析 ─┬─ T-824 模型控制面板
                   │                   └─ T-821-B1 参数层 ─ B2 缓存 UI ─ B3 教学弹窗
                   └─ T-820-A2 AuthStyle ─ T-820-A3 OAuth（可滑动）
T-822 前端预览 依赖 T-822 后端 + T-820-A1 前端
T-823 贯穿
```

## v0.820 任务（当前版本）

- [x] **T-830 P0** GitHub Copilot 设备码 / OpenAI Codex 设备码 + PKCE 粘贴；token 落盘与 refresh；登录弹窗
- [x] **T-831 P0** 群聊成员级 `reasoningEffort` / `fastMode`（generate 合并 + 成员设置 UI）
- [ ] **T-832 P1** Bedrock Converse / 原生 eventstream、Mistral Conversations、Vertex Anthropic `rawPredict`（可滑动）

### v0.820 已滑出

- T-806-6C Responses 内建 web_search（仍属 v0.800）
- 真实 API Key 缓存写→读探测（已搁置）

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
