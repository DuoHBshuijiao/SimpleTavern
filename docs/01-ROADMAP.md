# v0.600 -> v1.000 路线图

## v0.600 定位

`v0.600` 是“全局体验一致性与前端系统升级版本”。本版本将 v0.500 的稳定化基础推进到产品体验层：统一 surface/card/button/input/modal/drawer 视觉语言，收束硬编码视觉方言，并补齐主要弹层、主路径和高频面板的可访问性、性能与测试保护。

## v0.600 已完成

- 设计系统：新增/强化 Surface、Card、Button、Input、Modal、Drawer、Popover、Focus Ring、Z-Index 与 reduced-motion 基座。
- 高频主路径：统一聊天输入、消息气泡、聊天侧栏、助手面板、MVU 面板、TTS 浮层的 surface 与按钮状态。
- 设置与弹层：统一设置抽屉、导入导出、群聊设置、消息编辑、知识图谱、WebGPU、HTTP Log、世界书等弹窗外层与关闭按钮语义。
- 无障碍：补关键图标按钮 `aria-label`，新增通用 dialog Esc/焦点恢复工具并全量接入弹层（含 ChatPage 内联编辑弹层）。
- 性能：减少叠层 `backdrop-blur`，统一面板层级，保留列表/Markdown/KG/WebGPU/TTS 的轻量更新策略。
- 稳定性：MVU/知识图谱路由集中 chat fast-fail，404 返回结构化 `code/message/chatId`。
- 测试：补 UI primitive 与 dialog focus 工具测试，保留正文正则显示测试，新增 MVU route 错误测试。

## v0.600 边界

- 不拆分整个 `ChatPage.vue` 或 `SettingsDrawer.vue`。
- 不新增原生 Responses API、Anthropic Messages API、Gemini 原生 API 协议栈。
- 不做完整 Playwright E2E 或组件测试体系。
- 不做后端全局 chatId 索引迁移。

## v0.601 无障碍约束补强

- 固化“禁止原生元素裸用 `title` 属性，仅允许 `aria-label`（或可见文本 / `aria-labelledby`）”为设计规范（`DESIGN.md` / `PRODUCT.md`），并以前端测试守卫扫描全部 `.vue` 防止回归（PascalCase 组件 `title` prop 豁免）。

## v0.700 定位

`v0.700` 是「前端组件化 + 全面 UI/动画 + 可观测性」版本。在本版本内完成：

1. **组件化**：ChatPage / SettingsDrawer 渐进拆分与 composable 提炼（含生成流前的中低风险块；生成/SSE orchestration 在本版内排期但次于 UI 与低风险 composable）。
2. **UI/动画**：Impeccable 全量扫尾——圆角/滚动条 token 化、消除 side-tab、弹层/error surface 统一、动效 150–250ms 与 `prefers-reduced-motion`。
3. **可观测性**：数据完整性扩展、导入/导出 warning（已完成首批）。

**v0.800** 专注**后端性能改进**（索引、扫描、生成路径优化等），不再承担前端拆分与 UI 主责。

### v0.700 已完成（约 45%）

- 前端组件测试基座（`@vue/test-utils` + `happy-dom`）。
- ChatPage composable 第一批：`useChatSearch`、`useImageStickyBinding`、`useForkLineage` + 单测。
- 数据完整性扫描扩展 + 导入 warning 修复。
- UI/UX 首批：ChatPage 顶栏 + ChatSidebar 选中态 + 图片回退弹层 + 搜索 a11y + 完整性巡检文案。

### v0.700 进行中 / 待完成

| 批次 | 任务卡 | 内容 |
|------|--------|------|
| UI/动画 | T-209 | chat/modals/SettingsDrawer Impeccable 扫尾、`.custom-scrollbar` 全局化、side-tab 消除 |
| 组件化 | T-210 | ChatPage composable 第二批（入场动画、Esc 栈、reasoning、顶栏布局…） |
| 拆分 | T-211 | SettingsDrawer 渐进拆分 |
| 组件化 | T-212+ | ChatPage 角色编辑/导入导出子模块；`GenerationDeferState` 后拆生成/SSE |
| UI/动画 | T-213 | ChatInput sink 动效（去 margin transition）、全站 motion audit |
| 可观测性 | T-214 | orphan 扩展、导出 warning 等剩余项 |

### v0.700 边界

- 不新增原生 Responses / Anthropic / Gemini 协议栈。
- Playwright E2E 可推迟至 v0.900+，但组件测试基座在本版内继续扩展。

## v0.800 定位

**后端性能改进版本**：chatId 索引、扫描/加载路径优化、生成与 MVU 热路径 profiling、缓存与 I/O 批量化等。前端仅做性能相关的小幅配合（若必要），**不承担** SettingsDrawer/ChatPage 大拆与 UI 全面扫尾。

## v0.900+ / v1.000

- 协议层抽象（Responses / Anthropic / Gemini）。
- Playwright E2E、后端全局索引迁移（若未在 v0.800 完成）。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- 后端生成、MVU、正文正则、导入导出和数据完整性有基本测试保护。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
