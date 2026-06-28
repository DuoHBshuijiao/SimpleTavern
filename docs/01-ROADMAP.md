# v0.500 -> v1.000 路线图

## v0.500 定位

`v0.500` 是首个稳定化质量版本。它必须包含实际修复、测试和发布闭环，而不只是建立文档治理。

## v0.500 必做

- 前端：修复设置抽屉未保存更改丢失、MVU 草稿覆盖、overlay 叠层、Esc/确认框行为、正文正则显示语义和长会话 markdown 缓存上限。
- 后端：修复 LLM preset 静默回退、TTS preset 误用于 LLM、正文正则扫描器高频全库扫描、MVU 队列丢失/唤醒不可靠、无效角色创建脏会话、导入恢复静默失败。
- 测试：新增后端 pytest 入口，补正文正则、regex 兼容、队列、preset 解析和 OpenAI 兼容 URL 测试；前端补正文正则 golden 测试。
- 文档：README 改为稳定化维护状态，补齐已存在能力说明，新建 `CHANGELOG.md` 与 `docs/RELEASE-v0.500.md`。

## v0.500 不做

- 不做全面 Surface/Card 样式系统迁移。
- 不拆分整个 `ChatPage.vue` 或 `SettingsDrawer.vue`。
- 不新增原生 Responses API、Anthropic Messages API、Gemini 原生 API 协议栈。
- 不做完整 Playwright E2E 或组件测试体系。
- 不做后端全局 chatId 索引迁移。

## v0.510+ 方向

- 分阶段落地 Surface/Card 体系与样式令牌收束。
- 拆分巨型前端组件，提炼 settings/chat 专用子组件。
- 扩展数据完整性扫描范围和 UI。
- 逐步建立协议层抽象，为 Responses、Anthropic、Gemini 原生协议做准备。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- 后端生成、MVU、正文正则、导入导出和数据完整性有基本测试保护。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
