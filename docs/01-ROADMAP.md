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

`v0.700` 是“组件化与可观测性强化版本”。在不改变现有行为的前提下，建立前端组件测试基座、把 `ChatPage.vue` 中最内聚的低风险逻辑块提炼为 composable，并扩展后端数据完整性扫描与导入/导出可观测性，使长会话维护与数据修复更透明。

### v0.700 已完成

- 前端组件测试基座：引入 `@vue/test-utils` + `happy-dom`，建立可挂载 SFC 的组件测试模式与 `ThemedCheckbox` 示例。
- ChatPage composable 提炼（第一批，低风险、template 不变）：`useChatSearch`、`useImageStickyBinding`、`useForkLineage`，各配 composable 单测，类型检查 + 单测双重保护。
- 数据完整性扫描扩展：从仅 chat/assistant JSON 扩展到 `settings.json`、`assistant_settings.json`、`characters/`、`worldbooks/`，并新增 chat.characterId 的 orphan 引用检测；新增类别一律“仅检测、不自动修复”（repairAction=none），孤儿会话不会被按 chat 规则自动删除；前端巡检区分自动清理与人工处理。
- 导入/导出可观测性：修复导入提示互斥丢失 MVU 兼容 warning；TXT(Version 2) 会话导入透传此前被静默丢弃的逐行 warning。

### v0.700 未纳入（顺延 v0.800+）

- card.attachedWorldBookIds 悬空等更多 orphan 类型、导出跳过项告知、JSONL 之外更多导入路径的 warning 透传。

### v0.700 边界（推迟到 v0.800+）

- 不拆分 `ChatPage.vue` 的生成/SSE orchestration（共享 defer/reasoning/stream 状态，风险极高）。
- 不做 `SettingsDrawer.vue` 大规模 Tab 拆分（统一草稿 + 单次保存耦合深）。
- 不新增原生 Responses / Anthropic / Gemini 协议栈。
- 不做 Playwright E2E、不做后端全局 chatId 索引迁移。

## v0.800+ 方向

- 继续提炼 ChatPage 顶栏布局、TTS 策略、角色编辑等中风险块。
- 设计统一 `GenerationDeferState` 接口后再拆生成/SSE orchestration。
- 渐进拆分 SettingsDrawer（先 Teleport/Modal，再 Presets/Chat Tab）。
- 逐步建立协议层抽象，为 Responses、Anthropic、Gemini 原生协议做准备。
- 关键路径 E2E。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- 后端生成、MVU、正文正则、导入导出和数据完整性有基本测试保护。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
