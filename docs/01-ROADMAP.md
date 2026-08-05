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

### v0.700 已完成（100% 前端范围）

- 前端组件测试基座（`@vue/test-utils` + `happy-dom`）。
- ChatPage composable 第一批：`useChatSearch`、`useImageStickyBinding`、`useForkLineage` + 单测。
- 数据完整性扫描扩展 + 导入 warning 修复。
- UI/UX 首批：ChatPage 顶栏 + ChatSidebar 选中态 + 图片回退弹层 + 搜索 a11y + 完整性巡检文案。

### 已完成批次

| 批次 | 任务卡 | 内容 |
|------|--------|------|
| UI/动画 | T-209 | ✅ chat/modals/SettingsDrawer Impeccable 扫尾 |
| 组件化 | T-210 | ✅ ChatPage composable 第二批 |
| 拆分 | T-211 | ✅ SettingsDrawer Tab 拆分 |
| 组件化 | T-212 | ✅ ChatPage 弹层/composable（SSE 主体 → v0.800） |
| UI/动画 | T-213 | ✅ ChatInput sink + motion audit |
| 可观测性 | T-214 | ✅ 前端收尾（orphan 扩展/导出 API → v0.800） |
| 设计审计 | T-215 | ✅ Impeccable 语义 token/a11y/motion/caption-xs 收口 |

### v0.700 边界（已关闭）

- 不新增原生 Responses / Anthropic / Gemini 协议栈（已改排至 **v0.800**）。
- **不在 v0.700**：ChatPage SSE 主体 composable、后端性能、世界书 orphan 扩展、导出跳过 API warnings。
- Playwright E2E 可推迟至 v0.900+；组件测试基座已扩展。

## v0.800 定位

`v0.800` 是“**后端可信执行层**”版本，正式进入进行中状态。核心不是单点性能调优，而是把所有后端组件升级为可定位、可计量、可验证的执行系统。

### 核心原则

1. **Fast-Fail 全覆盖**：取消静默吞错、空结果伪成功与隐式供应商/模型 fallback。
2. **用户可感知错误**：REST、SSE、后台任务、工具调用统一结构化错误与 requestId，进入前端错误栈。
3. **性能 + 健壮性**：所有 backend 组件纳入基准、profiling、故障注入与回归门禁。
4. **原生多厂商协议**：OpenAI Responses、Anthropic Messages、Gemini 原生协议；保留 OpenAI-compatible。
5. **精确用量与成本**：消息元数据记录云端 usage、缓存、TTFT、总耗时、cost；本地账本支持会话/全局/按模型汇总。

### 主要交付

| 领域 | 交付 |
|------|------|
| 错误基座 | 统一错误 envelope、requestId、SSE terminal error、前端 typed error |
| 全后端迁移 | 审计并移除静默 fallback；所有 catch 有明确语义 |
| 性能 | HTTP client/连接池、chatId 与 usage 索引、生成/MVU/TTS/storage 热路径 |
| 原生协议 | OpenAI Responses、Anthropic Messages、Gemini；多套工具/消息/流事件适配 |
| Anthropic 缓存 | API 预设中显式启用 prompt caching，不支持时 fast-fail |
| 计量 | message generation metadata + append-only usage ledger |
| 成本统计 | 会话/全局切换、总/平均 token、缓存命中、总成本、按模型汇总 |
| 搜索 | Tavily/博查增强；独立搜索 API 与模型原生联网能力扩展 |
| 前端 SSE | `useChatGeneration` 消费统一 meta/usage/done/error |
| 数据完整性 | worldbook orphan、导出跳过 warning、索引修复 |

详细设计：

- `docs/tasks/T-800-v0800-backend-performance.md`
- `docs/tasks/T-801-v0800-fast-fail-foundation.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`

### 当前进度

- T-801 已完成：统一 REST/SSE 错误 envelope、requestId、上游错误映射、前端 typed error/错误栈。
- T-802 六批已完成：LLM/generate、Storage/chat/fork、Assistant/tools、MVU/KG/regex health、Search/Import-Export、TTS/infra（F-001~F-034）。
- T-804 已完成（协议内核 + OpenAI-compatible 迁入）。下一棒 T-805 原生协议。
- 当前门禁：后端 209 tests；fork 冷重建 410.05 ms；chat_path 重建 103.11 ms / 暖查找×1000 105.55 ms。

### 成本统计 UI

统计组件位于 SettingsDrawer → Global → “应用与更新”accordion 内，放在“成本计算器”按钮上方：

- 当前会话 / 全局切换。
- 总输入、总输出、平均输入、平均输出。
- 缓存读取输入、缓存写入输入、缓存命中率。
- 总金额与 cloud/local-estimated/unknown 来源区分。
- 按 provider/protocol/model 汇总 token、成本、请求数、TTFT 与总耗时。

### v0.800 边界

- 仍采用 JSON/JSONL + 文件锁，不引入传统数据库。
- 不做自动换模型、自动换供应商或隐藏协议降级。
- 模型价格匹配不允许宽泛别名直接产生确定成本；模糊项需用户确认。
- Playwright 全量 E2E 仍留 v0.900+。

## v0.900+ / v1.000

- Playwright E2E。
- 插件化 provider SDK、跨设备统计同步等后续能力。
- v0.800 未完成项不得仅因版本切换自动顺延，需在发布评审中明确。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- 后端生成、MVU、正文正则、导入导出和数据完整性有基本测试保护。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
