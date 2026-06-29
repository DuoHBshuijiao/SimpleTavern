# v0.600 -> v1.000 路线图

## v0.600 定位

`v0.600` 是“全局体验一致性与前端系统升级版本”。本版本将 v0.500 的稳定化基础推进到产品体验层：统一 surface/card/button/input/modal/drawer 视觉语言，收束硬编码视觉方言，并补齐主要弹层、主路径和高频面板的可访问性、性能与测试保护。

## v0.600 已完成

- 设计系统：新增/强化 Surface、Card、Button、Input、Modal、Drawer、Popover、Focus Ring、Z-Index 与 reduced-motion 基座。
- 高频主路径：统一聊天输入、消息气泡、聊天侧栏、助手面板、MVU 面板、TTS 浮层的 surface 与按钮状态。
- 设置与弹层：统一设置抽屉、导入导出、群聊设置、消息编辑、知识图谱、WebGPU、HTTP Log、世界书等弹窗外层与关闭按钮语义。
- 无障碍：补关键图标按钮 `aria-label`，新增通用 dialog Esc/焦点恢复工具并接入关键弹层。
- 性能：减少叠层 `backdrop-blur`，统一面板层级，保留列表/Markdown/KG/WebGPU/TTS 的轻量更新策略。
- 稳定性：MVU/知识图谱路由集中 chat fast-fail，404 返回结构化 `code/message/chatId`。
- 测试：补 UI primitive 与 dialog focus 工具测试，保留正文正则显示测试，新增 MVU route 错误测试。

## v0.600 边界

- 不拆分整个 `ChatPage.vue` 或 `SettingsDrawer.vue`。
- 不新增原生 Responses API、Anthropic Messages API、Gemini 原生 API 协议栈。
- 不做完整 Playwright E2E 或组件测试体系。
- 不做后端全局 chatId 索引迁移。

## v0.700+ 方向

- 拆分巨型前端组件，提炼 settings/chat 专用子组件。
- 扩展数据完整性扫描范围和 UI。
- 补充组件测试与关键路径 E2E。
- 逐步建立协议层抽象，为 Responses、Anthropic、Gemini 原生协议做准备。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- 后端生成、MVU、正文正则、导入导出和数据完整性有基本测试保护。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
