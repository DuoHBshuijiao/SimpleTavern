# v0.600 -> v1.000 路线图

仓库内不包含自动化测试。接口与界面规格见 `docs/specs/BACKEND-API.md` 与 `docs/specs/FRONTEND-FEATURES.md`。勿再加入 pytest / Vitest / Playwright。


## v0.600 定位

`v0.600` 是“全局体验一致性与前端系统升级版本”。本版本将 v0.500 的稳定化基础推进到产品体验层：统一 surface/card/button/input/modal/drawer 视觉语言，收束硬编码视觉方言，并补齐主要弹层、主路径和高频面板的可访问性与性能。

## v0.600 已完成

- 设计系统：新增/强化 Surface、Card、Button、Input、Modal、Drawer、Popover、Focus Ring、Z-Index 与 reduced-motion 基座。
- 高频主路径：统一聊天输入、消息气泡、聊天侧栏、助手面板、MVU 面板、TTS 浮层的 surface 与按钮状态。
- 设置与弹层：统一设置抽屉、导入导出、群聊设置、消息编辑、知识图谱、WebGPU、HTTP Log、世界书等弹窗外层与关闭按钮语义。
- 无障碍：补关键图标按钮 `aria-label`，新增通用 dialog Esc/焦点恢复工具并全量接入弹层（含 ChatPage 内联编辑弹层）。
- 性能：减少叠层 `backdrop-blur`，统一面板层级，保留列表/Markdown/KG/WebGPU/TTS 的轻量更新策略。
- 稳定性：MVU/知识图谱路由集中 chat fast-fail，404 返回结构化 `code/message/chatId`。
- 稳定性：补 UI primitive、dialog focus 与 MVU 路由错误语义（实现侧已不再保留自动化测试）。

## v0.600 边界

- 不拆分整个 `ChatPage.vue` 或 `SettingsDrawer.vue`。
- 不新增原生 Responses API、Anthropic Messages API、Gemini 原生 API 协议栈。
- 不做仓库内 Playwright 或组件测试体系。
- 不做后端全局 chatId 索引迁移。

## v0.601 无障碍约束补强

- 固化“禁止原生元素裸用 `title` 属性，仅允许 `aria-label`（或可见文本 / `aria-labelledby`）”为设计规范（`DESIGN.md` / `PRODUCT.md`）。PascalCase 组件的 `title` prop 仍表示可见标题。

## v0.700 定位

`v0.700` 是「前端组件化 + 全面 UI/动画 + 可观测性」版本。在本版本内完成：

1. **组件化**：ChatPage / SettingsDrawer 渐进拆分与 composable 提炼（含生成流前的中低风险块；生成/SSE orchestration 在本版内排期但次于 UI 与低风险 composable）。
2. **UI/动画**：Impeccable 全量扫尾——圆角/滚动条 token 化、消除 side-tab、弹层/error surface 统一、动效 150–250ms 与 `prefers-reduced-motion`。
3. **可观测性**：数据完整性扩展、导入/导出 warning（已完成首批）。

**v0.800** 专注**后端性能改进**（索引、扫描、生成路径优化等），不再承担前端拆分与 UI 主责。

### v0.700 已完成（100% 前端范围）

- 前端组件化基座（可挂载的 SFC 与 composable 拆分）。
- ChatPage composable 第一批：`useChatSearch`、`useImageStickyBinding`、`useForkLineage`。
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
- 仓库内不引入 Playwright 或其它自动化测试框架。

## v0.800 定位

`v0.800` 是“**后端可信执行层**”版本，正式进入进行中状态。核心不是单点性能调优，而是把所有后端组件升级为可定位、可计量、可验证的执行系统。

### 核心原则

1. **Fast-Fail 全覆盖**：取消静默吞错、空结果伪成功与隐式供应商/模型 fallback。
2. **用户可感知错误**：REST、SSE、后台任务、工具调用统一结构化错误与 requestId，进入前端错误栈。
3. **性能 + 健壮性**：所有 backend 组件纳入基准、profiling 与可观测错误语义。
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
- T-804 / T-805 已完成（四协议无工具主路径）。T-806-6A/6B/6C 已完成；「Gemini CachedContents」并入 v0.810 T-821（显式缓存策略）。
- T-807 已完成（消息 generationMetadata + usage ledger）。
- 性能基线（历史记录）：fork 冷重建 410.05 ms；chat_path 重建 103.11 ms / 暖查找×1000 105.55 ms。仓库内测试条数不再作为门禁。
- v0.800 剩余项（T-808~T-814）保留在 backlog，不因 v0.810 插入而自动顺延或删除。

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
- 黑盒测试在仓库外进行，依据 `docs/specs/`。

## v0.810 定位

`v0.810` 是插在 v0.800 协议内核之上的「**供应商目录 + 显式缓存 + 模型自适应**」小版本。API 预设功能自上次构建已过去数月：GPT-5.6+ 缓存策略要求显式断点、Anthropic 新增顶层自动 `cache_control`、Gemini 隐式/显式缓存分化、中国厂商多为尽力前缀缓存。本版本让用户用通俗字段把这些差异配置对，并在切换模型时自动选对协议与参数。

### 核心原则

1. **目录唯一信源**：内建供应商目录以 [pi `packages/ai/src/providers`](https://github.com/earendil-works/pi/tree/main/packages/ai/src/providers) 为唯一信源（模型元数据取 models.dev + OpenRouter `/models` 快照）；系统内已有的第三方供应商（如 Zenmux、硅基流动、智谱、百炼等）经核查数据安全受监管、调用记录可追溯，予以保留并映射到新目录。
2. **显式缓存、按协议写法**：`promptCache` 统一对象替代仅 Anthropic 的三档下拉；OpenAI Responses/Chat、Anthropic、Gemini、百炼各按官方写法发送；中国厂商默认尽力缓存不发多余字段。
3. **自适应协议不是隐藏降级**：`protocol: auto` 是用户可见、可关闭的模式；实际协议、推理深度夹紧、缓存翻译写入 SSE `meta.protocolResolution` 与预设编辑器预览。用户显式选定协议时永不改写。
4. **会话级模型控制面板**：聊天栏可一并切换模型、思考深度（含 `none` 真关思考与 `max`）、Fast 模式；不支持的档位灰显并说明原因。

### 主要交付

| 任务 | 交付 |
|------|------|
| T-820 供应商目录 | `sync_llm_catalog.py` + generated JSON + overlay；`GET /api/llm/catalog`；预设名称 combobox 分组/搜索/徽标；AuthStyle/URL 模板泛化（Azure/Vertex Express/Bedrock Anthropic）；OAuth 厂商（Copilot/Codex）允许滑至 v0.820 |
| T-821 显式缓存 | `promptCache` 字段与迁移；参数注册表；四协议缓存写法；Usage 缓存字段归一化；预设编辑器「缓存策略」区块；近全屏教学弹窗 |
| T-822 模型自适应 | `resolution.py`：auto 协议、家族匹配、effort clamp（含 `max`）、参数/缓存翻译；`POST /api/llm/resolve-preview`；协议下拉「自动」 |
| T-824 模型控制面板 | `ModelControlPanel.vue`；会话级 `params.reasoningEffort/fastMode`；四协议 `none` 关思考与 Fast 写法 |
| T-823 文档 | 路线图/backlog/任务卡/state/changelog/README 收口 |

### v0.810 边界

- 不做 Bedrock Converse 原生协议、Mistral Conversations API、Vertex Anthropic `rawPredict`。
- 群聊成员级思考深度/Fast → v0.820 backlog。
- 不引入数据库；Gemini cachedContents 索引仍是 JSON 文件。
- `backend/app/version.py` 已改为 `v0.810`。

## v0.820 定位

`v0.820` 接续 v0.810：把目录里标了「需登录」的厂商真正接上 OAuth，并把会话级思考深度 / Fast 补到群聊成员。不在本版扩新协议栈。

### 核心原则

1. **OAuth 凭证与 settings.json 分离**：access / refresh 落在 `data/oauth_tokens.json`，设置往返不会冲掉登录态；前端只看到是否已登录。
2. **设备码优先**：桌面 Web 收不了 Codex CLI 的 `localhost:1455` 回调；Copilot 走 GitHub RFC 8628，Codex 默认走 device-code，PKCE 仅提供「粘贴回调 URL」备用。
3. **群成员覆盖对齐既有 pick_param**：`runtime.params` → `memberSettings` → `chat.overrides.params` → 全局；`null` 表示沿用，显式 `false` 表示关 Fast。

### 主要交付

| 任务 | 交付 |
|------|------|
| T-830 OAuth | Copilot 设备码 + Copilot token 换发；Codex 设备码 + PKCE 粘贴；登录弹窗；`authStyle` oauth 发 Bearer；生成/列模型带厂商头 |
| T-831 成员级 | `GroupMemberSettings.reasoningEffort/fastMode`；成员设置弹窗；群聊 generate / rewrite 合并 |
| T-832 P1 | Bedrock eventstream / Converse / Mistral Conversations / Vertex `rawPredict`（本版可滑动） |

### v0.820 边界

- 不改 `version.py` 为 `v0.820`（发版时再改）。
- 不做 T-806-6C Responses 内建 web_search、真实 Key 缓存探测。
- 不做本机 `localhost:1455` 回调服务器。
- 不实现 Bedrock 原生 eventstream 解析（T-832，可滑）。

## v0.900+ / v1.000

- 仓库外黑盒测试（规格见 `docs/specs/`）；本仓库不引入 Playwright / pytest / Vitest。
- 插件化 provider SDK、跨设备统计同步等后续能力。
- v0.800 未完成项不得仅因版本切换自动顺延，需在发布评审中明确。

## v1.000 发布定义

- 现有功能稳定、文档准确、主要错误 fast fail 且可定位。
- 前端体验统一，主题和叠层行为可预测。
- `docs/specs/BACKEND-API.md` 与 `docs/specs/FRONTEND-FEATURES.md` 与产品行为一致。
- 每次任务都能通过 `docs/state/CURRENT.md` 和 `docs/state/LAST_HANDOFF.md` 接力。
