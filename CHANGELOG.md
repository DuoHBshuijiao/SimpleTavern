# Changelog

## v0.820（进行中）

### 并行沙箱

- 新增 `python sandbox.py`：独立 `data-sandbox/` 与端口 9181/9191，仅复制生产 `settings.json`，供浏览器点按且不改写生产 `data/`。用法见 `docs/SANDBOX.md`。

### 规格文档与拆除仓库内自动化测试

- 新增 `docs/specs/BACKEND-API.md`（全部 HTTP/SSE 功能与数据规范）与 `docs/specs/FRONTEND-FEATURES.md`（功能分区与可见控件清单）。
- 删除前后端单测、pytest / Vitest 依赖、测试专用重置函数与 `data-testid`。后续黑盒测试只依据规格文档、不接触源码。

### OAuth 登录（T-830）

- GitHub Copilot 设备码登录；OpenAI Codex 设备码 + PKCE 粘贴回调。
- Token 与设置分离；生成请求 Bearer + 厂商头。

### 群聊成员级思考 / Fast（T-831）

- `GroupMemberSettings` 增加 `reasoningEffort` / `fastMode`，优先级对齐群聊 `pick_param`。

## v0.810

### 供应商目录与鉴权（T-820 A1/A2）

- 以 pi providers 为信源生成 `providers.generated.json` / `models.generated.json`，overlay 补中文标签、协议、缓存策略；`GET /api/llm/catalog`。
- 预设名称 combobox 按国内 / 国际 / 网关 / OAuth 分组，选择联动 protocol / authStyle / providerParams。
- AuthStyle：`bearer` / `x-api-key` / `api-key`（Azure 可附 `?api-version=`）/ `x-goog-api-key` / `query_key`。
- AWS Bedrock Anthropic 变体：invoke URL 含 model、请求体去掉 `model`、写入 `anthropic_version: bedrock-2023-05-31`。原生 eventstream 流式本版 fast-fail。
- Copilot / Codex OAuth 滑到 v0.820。

### 分协议显式缓存（T-821）

- `promptCache` 对象替代仅 Anthropic 的三档；OpenAI / Anthropic / Gemini / 百炼按官方写法；中国厂商默认尽力缓存。
- Gemini `cachedContents` 本地索引，404 重建一次；消息气泡显示缓存读/写徽标。
- 近全屏 `PromptCacheGuideModal` 七步教学。

### 模型自适应协议（T-822）

- 协议下拉「自动（按模型选择原生协议）」；钉住协议永不改写。
- 思考深度增加 `max`，按模型能力向下夹紧；结果写入 SSE `meta.protocolResolution` 与预设预览。

### 聊天模型控制面板（T-824）

- 聊天栏胶囊：模型 + 思考深度 + Fast；`none` 在四协议路径上真正关闭思考。
- 全局/预设「回传思考内容」三态；DeepSeek 关闭回传时的 400 错误卡可跳到对应开关。

### 核对

- 当时 `npm run build` 通过。自动化单测条数仅作历史记录，现已拆除。
- `backend/app/version.py` 已改为 `v0.810`。

## v0.800（进行中）

### 本地定价与用量仪表盘（T-808）

- 写入 metadata 时按目录/用户价格表估算；云端 `cost.source=provider` 不被覆盖；未知不计 0。
- 别名与正则有效部分最短 3 字符。用户覆盖 `data/pricing_rules.json`。
- `GET /api/usage/summary|models|events`、`GET/PUT /api/pricing/rules`。
- 设置「应用与更新」内、成本计算器上方：当前会话/全局、时间范围、token/缓存/成本来源/按模型表。

### 搜索供应商与原生联网（T-809）

- 独立搜索增加 Brave Search（GET + `X-Subscription-Token`）；429 为配额错误。
- Anthropic `web_search_20250305`、Gemini `googleSearch`；与 Responses 一样不走本地 Tavily 循环、失败不静默换供应商。

### 领域性能说明与异常可见（T-810）

- 沿用 T-803 基线数字，未发明无测量加速。
- `GET /api/health` 暴露锁/正文正则/TTS 缓存/迁移警告；TTS 设置页展示缓存巡检 `lastError`。

### 世界书孤儿与锁超时（T-811）

- 完整性扫描 `orphan_worldbook`（引用的世界书不存在，不自动修）。
- 文件锁等待 30s 超时 → `file_lock_timeout` 503；health `locks.timeoutCount`。

### 前端 SSE 提炼（T-812）

- `useChatGeneration` 统一消费 meta/usage/delta/reasoning/done/error。
- 停止或失败 persist 本地流式消息，不 reload 冲掉正文。

### 迁移与隐私（T-813）

- `data/migration_warnings.jsonl`：旧设置缺扫描深度/预设 protocol 时可见警告。
- 账本与 repair 队列脱敏；旧 JSON `extra="allow"` 仍可加载。

### Responses 内建 web_search（T-806-6C）

- 主聊天 `webSearchEnabled`：协议为 `openai_responses` 时把 `{type:web_search}` 交给厂商，不要求本地 Tavily/博查 Key，也不走函数工具循环。
- 其它协议仍用 Tavily/博查；未配置则 `web_search_not_configured`。Responses 失败不静默改走 Tavily。
- adapter 跳过 `web_search_call` 输出项与流事件；其它 hosted tools 仍 fast-fail。

### 用量账本（T-807）

- 助手消息 `generationMetadata`（requestId / provider / protocol / usage / timing / cost）。
- append-only `data/usage/YYYY-MM.jsonl`，`eventId` 幂等；写失败 `usage_persist_failed` + `repair.jsonl`。
- 无云端 cost 时标记 unknown，不填 0。定价引擎与统计 API 归 T-808。

### 多协议工具 round-trip（T-806-6B）

- Anthropic Messages：OpenAI 形 tools ↔ `tool_use`/`tool_result`；流式 finish 携带 tool_calls。
- Gemini generateContent：`functionDeclarations` / `functionCall` / `functionResponse` 往返。
- OpenAI Responses：function tools（`function_call` / `function_call_output`）；内建 web_search 仍 fast-fail（归 6C）。
- 前端协议下拉去掉「无工具」标注；后端 280 项测试通过。

### Anthropic Prompt Cache（T-806-6A）

- 预设/全局增加 `anthropicPromptCache`：`off`（默认）| `5m` | `1h`；布尔旧值 true→`5m`、false→`off`。
- 仅 `anthropic_messages` 时设置页展示；adapter 在稳定 system 块注入 `cache_control`（不静默去掉缓存重试）。
- generate / assistant / mvu / TTS 文本后处理经 `attach_protocol_extra_body` 传递。
- 后端 270 项测试通过。

### OpenAI Responses（T-805-5D）

- 新增原生 `openai_responses` 适配器：`/v1/responses`、typed SSE、`store=false`。
- `output_text` / reasoning summary；工具与内建 web_search 本批 fast-fail（归 T-806）。
- T-805 四协议批次关闭；后端 262 项测试通过。

### Gemini generateContent（T-805-5C）

- 新增原生 `gemini_generate_content` 适配器：`generateContent` / `streamGenerateContent?alt=sse`。
- 拒绝 Base URL 含 `/openai`；工具/functionCall 本批不支持；`thought`→reasoning。
- 后端 253 项测试通过。

### Anthropic Messages（T-805-5B）

- 新增原生 `anthropic_messages` 适配器：Messages 请求转换、nonstream/stream、thinking→reasoning。
- 工具调用与 cache_control 本批不支持（工具/缓存三档归 T-806）；缺省 max_tokens=4096。
- 后端 243 项测试通过。

### 原生 LLM 协议接线（T-805-5A）

- `ApiPreset` / 全局 LLM 增加 `protocol`；`preset_resolve` 与 `llm/runtime` 经 registry 调用。
- generate / assistant / mvu / web_search / test-models 传递协议；SSE meta 反映实际协议。
- 设置页协议下拉；未实现协议（Anthropic/Gemini/Responses）明确 fast-fail。
- 审查修复：前端未知协议不再静默改写；ST MVU 导入与 TTS 文本后处理改走 runtime；未知协议 provider 标为 `unknown`。
- 后端 232 项测试通过。

### LLM 协议内核（T-804）

- 新增 ProviderAdapter / registry / GenerationConfig·WireRequest·Usage 类型。
- OpenAI-compatible Chat Completions 迁入 `providers/openai_compatible_chat.py`；`openai_compat` 保持兼容门面。
- 未知协议 fast-fail（`provider_capability_unsupported`）；后端 226 项测试通过。

### 性能基础设施 3D（T-803）

- generate 世界书/trim 抽取为共享 prep，并记录分段耗时与计数。
- 新增世界书激活索引：热路径只加载激活世界书正文；启动预热。
- `ensure_mvu_worker` 可复用已加载 chat/character；扫描窗口未变时复用 match。
- 基线：20 书/2 激活 prep 约 5 ms；后端 220 项测试通过。T-803 批次关闭。

### 性能基础设施 3C（T-803）

- 正文正则后台扫描改为单次路径枚举，去掉群聊/角色目录双载。
- 按文件 mtime/size 与规则签名跳过未变更会话；扫描读使用共享锁且不附加长期记忆。
- portalocker 等待时长可观测；`/api/content-regex/health` 暴露扫描耗时与跳过统计。
- 基线：100 会话冷扫约 130 ms、暖扫约 17 ms；后端 214 项测试通过。

### 性能基础设施 3B（T-803）

- 新增 `chat_path_index`（chatId→characterId/format），`load_chat` 热路径不再全角色目录扫描。
- save/delete 挂钩索引维护；应用启动预热路径索引。
- 基线：1000 会话重建约 103 ms；暖查找 ×1000 约 106 ms；后端 209 项测试通过。

### 性能基础设施 3A（T-803）

- 新增进程级共享 HTTP client（连接池 + 默认超时），应用 lifespan 负责启动/关闭。
- OpenAI-compatible LLM 与网络搜索出站请求改为复用共享 client，保留请求级 timeout。
- 后端 204 项测试通过。

### 静默 Fallback 迁移第六批（T-802）

- GLM 本地 TTS：JSON 合成失败回退 multipart 时写入 `tts_endpoint_fallback`（from/to/reason），响应附带 warnings。
- SiliconFlow 音色列表远程失败时保留内置预设，并返回 `tts_voice_list_partial` / `partialSuccess`。
- GLM 本地进程托管暴露 failureCount/lastError/code；health/start API 返回结构化 health。
- 出站 HTTP 日志写失败计数，并新增 `/api/http-log/health`。
- Tokenizer 不可用保持 null/unavailable，不再被 generate 用 `or 0` 伪装；新增 `/api/tokenizer/health`。
- 后端 198 项测试通过；T-802 清单 F-001~F-034 主项迁移完成。

### 静默 Fallback 迁移第五批（T-802）

- 网络搜索 provider 失败改为结构化 `{ok, code, message}`；助手工具返回 `ToolResult.err`，不再把错误塞进成功工具结果字符串。
- 角色导出 ZIP 写入 `manifest.json`（`warnings` / `partialSuccess` / `exportedWorldBookIds`），缺失世界书记为 `export_attachment_missing`。
- 导入 warning 统一为 `{code, message, ...}`；前端兼容旧字符串与新结构。
- 静默 fallback 守卫扩展到 web_search / import_export；后端 191 项测试通过。

### 静默 Fallback 迁移第四批（T-802）

- MVU worker / 正文正则 scanner 增加 health（failureCount、lastError、paused、nextRetryAt），并暴露 `/api/mvu/{chatId}/health` 与 `/api/content-regex/health`。
- MVU SSE QueueFull 与正文正则队列超限分别计数 `sseDropped` / `queueDropped`，不再静默丢弃。
- 角色不可读与 MVU 未开启分离为 `mvu_character_unreadable`；KG 门控透传结构化 code。
- MVU 工具非法 JSON 改为 `tool_call_invalid` ToolResult；世界书坏 regex 进入 generate SSE meta.warnings。
- 后端 185 项测试通过。

### 静默 Fallback 迁移第三批（T-802）

- 助手消息保存前严格校验，非法 tool/assistant 组合抛 `assistant_message_invalid`，禁止脏对象落盘。
- 助手工具参数非法 JSON/非对象改为 `tool_call_invalid` ToolResult，不再退 `{}` 执行；executor 同步拒绝非 dict。
- 助手非流失败改为 AppError envelope；流式错误携带 terminal ErrorEnvelope，并补齐 SSE meta/requestId。
- 工作区角色卡草稿缺失/损坏分别返回 `data_not_found`/`data_corrupted`；成功直接返回 CharacterCard。
- 新增 assistant 错误契约测试与静默 fallback 守卫扩展；后端 178 项测试通过。

### 静默 Fallback 迁移第二批（T-802）

- 损坏角色/世界书在保持列表数组兼容的同时进入数据完整性巡检；直接加载损坏角色、世界书、会话改为 `data_corrupted`，不再伪装未找到。
- runtime chat issue 保持完整校验直到文件真正修复；瞬时读取错误只允许人工处理，不触发自动删除。
- 损坏 fork index 可从会话元数据重建并返回粘性 warning；重建失败可重试，索引同步失败不覆盖已保存会话。
- cleanup-only 失败统一结构化日志与 requestId，目录清理保持逐项尽力执行；损坏 update-ignore 不再被覆写为空对象。
- 瞬时并发写/读失败不再误清已有完整性 issue；只有稳定确认恢复或文件消失时才清除。
- 1000 会话、99 fork 冷重建基线为 410.05 ms；后端 169、前端 123 项测试与前端构建通过。

### 静默 Fallback 迁移首批（T-802）

- 建立全 backend 八领域 fallback/catch 首轮 P0/P1 清单，区分 fatal、partial、retryable、explicit-fallback、cleanup-only 与 verify-first。
- 模型列表空结果不再回退本地候选或返回 200 + `[]`；OpenAI-compatible 空响应、非法 SSE、空流与断流改为结构化错误。
- 网络搜索工具坏参数/未知工具不再退 `{}` 执行；group/interject 搜索未配置在生成前 fast-fail。
- draft-help/group/interject 对齐 requestId、SSE meta/terminal error/success-only done 与非流 ErrorEnvelope。
- 新增已迁域静态 silent-fallback 守卫与协议/路由运行时回归测试；后端 150、前端 121 项测试与前端构建通过。
- 确认 generate 不调用正文正则管线；产品语义定为 A（存原文 + 前端显示时处理），F-010 关闭。

### Fast-Fail 错误基座（T-801）

- 新增统一 `AppError` / `ErrorEnvelope`、全局 REST 异常处理和贯穿普通/异常/流式响应的 requestId。
- 统一 SSE `meta`、terminal `error`、success-only `done`；前端收到 error 后终止消费，不再处理后续 done。
- 增加上游鉴权、配额、超时、网络和非法响应映射；未处理异常不向 UI 泄露堆栈。
- `/llm/test-models` 失败不再以 200 + 空数组伪装成功；单聊生成和网络搜索未配置路径完成首批迁移。
- 前端新增 typed `ApiError`，兼容旧 FastAPI detail/裸文本错误；错误栈展示建议操作和 requestId。
- 出站 HTTP 日志关联 requestId，并补 Authorization、API Key 与 cookie 脱敏。
- 新增 REST/SSE/requestId/redaction/模型列表 fast-fail 及前端解析/展示测试；后端 129、前端 121 项测试与前端构建通过。

### 版本启动

- 正式进入 v0.800 规划阶段；本轮仅更新文档，应用版本常量仍为 `v0.700`。
- 版本主题升级为“后端可信执行层”：全 backend fast-fail、取消静默 fallback、统一用户可感知错误、性能与健壮性增强。
- 原生 OpenAI Responses、Anthropic Messages、Gemini 协议从 v0.900+ 调整到 v0.800，并纳入多套工具调用、消息维护与流式事件适配。
- 规划 Anthropic prompt caching 显式开关；不支持/失败时不静默重发无缓存请求。
- 规划消息 generation metadata 与 append-only usage ledger，记录云端 token、缓存读取/写入、TTFT、总耗时与 cost。
- 规划 SettingsDrawer “应用与更新”中的会话/全局/按模型 usage/cost 统计，位于成本计算器按钮上方。
- 规划扩展独立搜索 API 与 OpenAI/Anthropic/Gemini 原生联网能力；失败不得自动切换供应商。
- 新增 T-800 总卡、T-801 Fast-Fail 首批任务卡与后端可信执行层设计文档。

## v0.700

### 组件化与测试基座

- 引入前端组件测试基座：新增 `@vue/test-utils` + `happy-dom`，建立可挂载 SFC 的组件测试模式与 `ThemedCheckbox` 示例。
- 从 `ChatPage.vue`（约 7166 行）提炼 3 个低风险 composable，行为不变并各配单测：`useChatSearch`（会话内搜索状态机/动画时序/导航）、`useImageStickyBinding`（图片占位粘性绑定 + 生成失败回退对话框）、`useForkLineage`（分叉血缘加载/缓存/防抖/切会话清理）。

### 数据完整性与导入可观测性

- 数据完整性扫描从仅 chat/assistant JSON 扩展到 `settings.json`、`assistant_settings.json`、`characters/`、`worldbooks/`，并新增 chat.characterId 的 orphan 引用检测。新增类别一律“仅检测、不自动修复”（repairAction=none），孤儿会话所在文件不会被按 chat 规则自动删除。
- 启动巡检前端区分“可自动清理”与“需人工处理”两类，绝不自动改动设置/角色/世界书。
- 修复导入结果提示在存在顶层 warning 时丢失 MVU 兼容 warning 的互斥问题；TXT(Version 2) 会话导入透传此前被静默丢弃的逐行 warning。

### 测试

- 新增前端 `ThemedCheckbox`、`useChatSearch`、`useImageStickyBinding`、`useForkLineage`、`formatImportResultMessage`、`dataIntegrityNotify` 测试；新增后端数据完整性扩展、导入 warning 透传测试。前端 88 测试、后端 114 测试全通过。

### UI/UX

- 收束 ChatPage 顶栏 chip / 更多菜单圆角到设计 token；新增 `--radius-track` 统一细滚动条滑块。
- ChatSidebar 群聊/单聊列表移除 side-tab 左侧色条，改用 `surface-selected` 选中态（符合 DESIGN.md 禁止 side-stripe 规则）。
- 图片回退弹层对齐 `modal-surface` 与语义 error token，去除硬编码 red-* 色值。
- 会话搜索区补 `role="search"` 与导航按钮 `aria-label`；数据完整性巡检展示 kind 标签并优化文案。

### UI/动画扫尾（T-209）

- 新增 `--radius-scrollbar`、`--radius-xs`；全局 `.custom-scrollbar` 收束至 `scrollbar.css`，删除各组件重复 scoped 块。
- SettingsDrawer 正文正则列表移除 `border-l-4` side-tab，改用 `surface-selected`。
- Impeccable detect 通过 chat/modals/SettingsDrawer（ChatInput `margin-top` 动画留 T-213）。

### ChatPage composable 扩展（T-210 完成）

- 新增 `useMessageListEnterAnimations`、`useGlobalEscapeStack`、`useMainChatReasoning`、`useChatHeaderLayout`、`useChatFabSeparation` 及单测；ChatPage 接入。

### SettingsDrawer 拆分（T-211 完成）

- Global / Presets / Chat 三 Tab 拆至 `components/settings-drawer/`；Presets ref 绑定 Bugbot 修复。

### ChatPage 拆分（T-212 完成，SSE 留 v0.800）

- 角色/Persona/PNG-ST/助手设置弹层 + `useCharacterEditor` / `useEmbeddedAvatarImport` / `useGenerationDeferState`。
- 生成/SSE 主体 composable 推迟 v0.800（与后端性能同批）。

### UI/动画（T-213）

- ChatInput sink 使用 morph-wrap `transform` + 外壳等量负 margin 布局补偿，二者同频过渡；SettingsDrawer 动效收束至 motion token。

### 可观测性收尾（T-214）

- 完整性巡检 `formatIssueLine` 展示 `detail`（如 orphan characterId）；Janitor 导入统一 `formatImportResultMessage`。
- v0.700 文档收口；worldbook orphan / 导出 API warnings / SSE composable → v0.800；多厂商协议 → v0.900+。

### 测试

- 截至 v0.700 收尾：前端 113 测试、后端 117 测试全通过。

## v0.601

### 无障碍

- 新增设计规范约束：禁止在原生元素上使用裸 `title` 属性作为提示或可访问标签，统一改用 `aria-label`（或可见文本 / `aria-labelledby`），并写入 `DESIGN.md` 与 `PRODUCT.md`。
- 新增前端测试守卫 `frontend/src/utils/noBareTitleAttr.test.ts`：扫描全部 `.vue`，断言原生元素不出现 `title` / `:title` 属性（PascalCase 组件的 `title` prop 不受影响），防止该约束回归；当前代码 0 违规。

## v0.600

### 系统性升级

- 建立统一的 Surface/Card/Button/Input/Modal/Drawer/Popover 视觉语言，补齐焦点环、loading、danger、secondary、disabled、active 与 reduced-motion 状态。
- 收束主要页面和面板中的硬编码颜色、阴影、圆角、z-index 与多层 `backdrop-blur`，让聊天列表、消息气泡、输入区、侧栏、设置抽屉、助手/MVU/TTS 面板、知识图谱和 HTTP Log 的视觉层级更一致。
- 统一导入导出、群聊设置、消息编辑、WebGPU、世界书、知识图谱等弹窗外层 surface，并补充关键关闭按钮 `aria-label`、dialog 标题关联、Esc 与焦点恢复工具；全量弹层接入 `useDialogBehavior` / `dialogAria`。
- 优化高频交互的微动效与性能表现，减少重面板模糊叠层，保留列表渲染、Markdown 缓存、KG/WebGPU/TTS 面板的轻量更新策略。

### 稳定性与测试

- MVU/知识图谱路由集中会话加载 fast-fail，缺失会话返回结构化 `code/message/chatId`，便于前端和用户定位问题。
- 新增前端 UI primitive、dialog focus 工具测试，保留正文正则显示测试；新增后端 MVU route 错误测试。

## v0.500

### 修复

- 统一 LLM API 预设解析，显式预设不存在、误选 TTS 预设或缺少凭证时会 fast fail，不再静默回退到其他端点。
- 修复 MVU worker 首次启动时清空正文正则队列导致提取结果丢失的问题，并在队列入队后唤醒 worker。
- 修复正文正则扫描器高频全库扫描、异常静默吞掉和首条 greeting 入队问题。
- 修复单聊创建时角色不存在仍创建脏会话的问题。
- 修复 ZIP 导入长期记忆失败时无 warning 的问题。
- 修复设置抽屉关闭会丢弃未保存更改、MVU 草稿被外部刷新覆盖、抽屉叠层被助手/MVU 面板遮挡的问题。
- 修复前端正文正则显示处理与后端替换语义不一致的问题。

### 改进

- 新增后端 pytest 基线，覆盖正文正则、regex 字面量、队列、API 预设解析和 OpenAI 兼容 URL。
- 新增前端正文正则 golden 测试。
- 为 MessageList markdown HTML 缓存增加 LRU 上限，降低长会话内存增长风险。
- 统一高风险确认框到应用内通知系统，并增强 Esc/焦点行为。
- README 改为 v1.0 稳定化维护状态，并补齐 MVU、正文正则、知识图谱、会话分叉和数据完整性说明。
- 新增 `docs/` 任务接力与 `docs/RELEASE-v0.500.md` 发布清单。
