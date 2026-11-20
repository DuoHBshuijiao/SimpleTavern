# Simple Tavern 项目现状审计

审计日期：2026-09-29（Asia/Hong_Kong）  
范围：当前工作树代码、配置、文档、Git 近期历史及安全可运行的前端构建。未修改源码；本次新增本报告。仓库当时已有未跟踪 `.agents/`、`.codex/`，不属于本次改动。

## 阅读约定与结论可信度

- **FACT**：由当前代码、配置、提交记录或本次命令直接确认。
- **INFERENCE**：根据已确认实现推导出的效果或风险。
- **RECOMMENDATION**：面向后续决策的建议，不代表已实现。
- 除已运行的前端 build 外，没有运行服务器、联网供应商请求或破坏性操作。仓库明确要求不保留自动化测试框架，因此未执行不存在的测试。
- 当前版本事实：`backend/app/version.py` 为 v0.810；文档和近期提交又记录了 v0.820 的 OAuth 与群聊成员参数落地，版本号没有跟进。

## 1. 当前定位

**FACT：**Simple Tavern 实际上是一个以单个可信用户、本机持有数据为默认场景的 AI 角色扮演工作台。用户管理角色卡、聊天、Persona、World Book、会话记忆、群聊、模型连接、工具、TTS 和视觉背景，并让本机 FastAPI 服务连接外部模型服务。它不是纯前端聊天网站，也不是多租户 SaaS。

- 核心流程：启动本地后端与 Vue UI → 选择/导入角色 → 配置厂商预设/API 凭据 → 创建或打开会话 → 输入消息 → 后端组装角色/Persona/世界书/历史上下文并调用模型 → SSE 流式回传 → 本地 JSON 文件保存 → 可选后处理、TTS、MVU/助手工具。
- 平台：UI 是浏览器 Web 应用；仓库提供 Windows 启动/更新/部署脚本及 POSIX `deploy.sh`。**未发现** Electron/Tauri 原生桌面壳或 Android/iOS 原生客户端。桌面体验依赖本机运行服务，但技术上可在配置 CORS 与 bind 后经 LAN/远端访问，远程场景尚非安全完整的多用户服务。
- Desktop：桌面浏览器使用本地 UI+本地 Python 服务是最自然部署；称为“桌面应用”是产品体验描述，不等于有独立原生打包。
- Mobile：存在窄屏/竖屏探测和大量响应式 UI 细节，但无 manifest、service worker、PWA/offline 安装能力，也没有移动端专用客户端。移动端可访问能力不等于后台可靠、随身可用。
- 前后端：Vue 3 + TypeScript + Pinia 通过 `/api` 调 FastAPI；Vite dev server 默认代理到 `127.0.0.1:9091`，UI 默认 9081。后端转发至 OpenAI Compatible、OpenAI Responses、Anthropic Messages、Gemini 等厂商 API；通常需要互联网/API 凭据。
- 本机依赖：数据、角色、聊天和设置由本机 Python 文件系统服务管理；本地 TTS 引擎也可单独拉起。Web 页面本身不直接拥有数据目录访问权。
- Local-first：**部分成立**。用户数据默认在本地 JSON/文件中、无强制云账户/同步；推理常依赖远程模型，搜索和平台 TTS 也可能依赖第三方。没有数据库同步、跨设备同步或端到端加密体系。故“本地数据控制”成立，“离线完整可用”不成立。
- 远程部署：FastAPI 的 CORS 可通过 `SIMPLETAVERN_CORS_ORIGINS` 扩展，bind 可配置，Vite preview 有 host 设置；deploy 脚本/更新路由存在。未见登录/用户隔离/API 授权作为远程多用户边界。**推断：**暴露到公网不应等同于受支持的安全部署模式。
- 用户模型：设置、数据目录和全局服务是单用户取向；没有 user/tenant 身份模型。并发文件锁解决本地并发写，不构成多用户授权与隔离。

状态归类：当前运行代码已实现 Web UI、API 后端、本地 JSON 持久化、流式生成、多个模型协议、角色/会话/导入导出及 TTS 等；部分实现是移动浏览器适配、远端访问和 local-first；文档规划但未实现/未完成包括 T-814 黑盒规格核对、T-832 额外协议；PWA/原生移动端/多用户服务未发现；已有少量 legacy 字段/迁移逻辑仍在运行。

## 2. 仓库结构地图

| 路径 | 核心职责 → 主要依赖 → 被谁调用 |
|---|---|
| `frontend/src/main.ts`, `App.vue`, `router/index.ts` | Vue 应用入口/路由 → Pinia、视图、全局 CSS → Vite 页面入口 |
| `frontend/src/views/ChatPage.vue` | 聊天主流程、发送/群聊/重写等页面编排；仍是大型编排中心 → stores/composables/API/components → 路由加载 | 
| `frontend/src/components/chat/MessageList.vue` | 虚拟窗口/消息交互渲染 → Markdown、消息类型、滚动测量 → ChatPage |
| `frontend/src/composables/useChatGeneration.ts`, `useStreamOutput.ts`, `frontend/src/api/sse.ts` | SSE 解码、增量缓冲、生成事件归一/流生命周期 → fetch/Pinia → ChatPage |
| `frontend/src/stores/{chats,characters,settings,ui}.ts` | 前端状态缓存及动作 → `src/api/*` → 视图/composable |
| `frontend/src/api/` | HTTP、SSE、各领域 REST 客户端 → 后端 `/api` → stores/视图 |
| `backend/app/main.py` | FastAPI 入口、CORS、lifespan、路由注册、后台巡检/索引预热 → storage/services/routes → 启动脚本 |
| `backend/app/routes/generate.py` | 普通/群聊/插话/草稿帮助生成、prompt/context、SSE 和消息保存 → schemas/storage/tokenizer/LLM/services → main 路由注册 | 
| `backend/app/llm/{types,protocol,registry,runtime,resolution}.py`, `providers/` | provider 协议/请求解析、adapter registry、请求运行及协议适配 → HTTP client、preset/catalog → generate、llm routes |
| `backend/app/schemas.py` | Pydantic 数据及请求 schema，允许多数实体 `extra="allow"` → routes/storage → 全后端 |
| `backend/app/storage.py` | JSON 路径、锁、读写、实体 CRUD、迁移/索引维护 → Pydantic、portalocker、索引 → routes/services |
| `backend/app/services/` | assistant agent/tools、TTS、多供应商搜索、usage、MVU daemon、KG、迁移等领域逻辑 → storage/LLM/client → routes/后台任务 |
| `backend/app/assistant_tools/` | 工具注册、上下文、执行器和 handlers（workspace/chat/worldbook/search/MVU/KG/regex）→ storage/services → assistant route/agent |
| `backend/app/tokenizer_service.py`, `backend/tokenizer/` | tokenizer 初始化、估算、窗口裁剪 → tokenizer 资源 → generate/context |
| `backend/app/routes/{chats,characters,worldbooks,settings,import_export,tts,assistant}.py` | REST API 分域入口 → schemas/storage/services → `main.py` |
| `frontend/src/composables/useGroupChat.ts`, `stores/*`; `backend/app/schemas.py`, `routes/generate.py` | 群聊 UI 编排、成员状态与后端成员级生成设置/提示身份 → chats、characters、generate → ChatPage |
| `frontend/src/composables/useTtsPlaybackQueue.ts`, `backend/app/routes/tts.py`, `services/tts_*` | 浏览器播放队列与后端合成/缓存/本地进程/供应商调用 → message metadata/cache → ChatPage/播放 FAB |
| `frontend/src/composables/useWebGpuBackground*.ts`, `utils/webgpu*`, `backend/app/routes/shader_presets.py` | WebGPU 渲染与 WGSL preset（前端主导）→ GPU canvas/browser API、后端预设存储 → 应用 shell/settings |
| `data/` | 活跃/示例用户数据及运行产物：JSON、头像、TTS/cache/log、索引、lock 等 → storage → 应用运行；不应把当前目录内容等同于干净安装状态 |
| `docs/specs/`, `docs/tasks/`, `docs/state/`, `docs/01-ROADMAP.md` | API/UI 对照规格、任务卡、状态交接与计划 → 人工维护 → 开发/黑盒核对 |
| `extensions/simpletavern-janitor-bridge/` | 浏览器扩展桥接外部 Janitor 页面导入 → content/background scripts → 浏览器扩展端 |
| 根目录 `deploy.*`, `update.*`; `backend/requirements.txt`; `frontend/package.json`, `vite.config.ts` | 环境部署、后端依赖、前端 build/dev → 本机工具链 → 用户启动/发布 |

架构中心：运行时最重心是 `backend/app/routes/generate.py`（多条对话生成路径共享若干 helper，但 prompt 构造与调度仍内聚于 route）；持久化中心是 `storage.py`；前端编排中心是 `ChatPage.vue`。LLM provider 边界已比业务生成边界清楚，`runtime.py` 经 adapter registry 派发到协议实现。

## 3. 一条消息生成的真实调用链

1. 用户在 `frontend/src/components/chat/ChatInput.vue` 输入并提交；页面接收事件并进入 `frontend/src/views/ChatPage.vue` 的发送/生成编排（大量业务仍在该文件）。单聊创建本地 assistant 占位消息、构造 `GenerateStreamRequest`，请求 API helper。
2. `frontend/src/api/sse.ts` 使用 fetch/ReadableStream 解码 SSE；`useChatGeneration.ts` 处理 `meta`、`usage`、`delta`、`reasoning`、`done`、`error`。delta 经 `useStreamOutput.ts` 缓冲后 patch Pinia `stores/chats.ts` 的本地消息，停止/错误时由页面选择保留本地流或 reload。
3. FastAPI `main.py` 注册 `routes/generate.py`；`POST /api/generate/stream` 对应 `generate_stream(req, request)`。先 `load_chat(req.chatId)`、读取 settings/character，解析当前 persona、模式、模型 preset/runtime、会话设置；无效配置转结构化错误。
4. 生成路径可以先更新用户消息并 `save_chat(chat)`。会话由 `backend/app/storage.py` 定位：`chat_path_index` 命中，缺失/陈旧则回退扫描；读 JSON 并 Pydantic 验证。角色来自 `characters/{id}.json`；persona 通常是 settings 中的 persona 集合与 `chat.userPersonaId` 引用；长期记忆单独存 `chat_memory.json`，同时 `ChatOverrides.longTermMemory` 是运行时读取/历史兼容字段。
5. `generate.py` 构造 system prompt：globalSystem（受 session prompt 模式控制）、Persona 名称/描述、角色名称/description/personality/scenario/systemPrompt、example dialogue 和 greeting 前缀、会话 prompt、runtime prompt、占位符与身份 XML 标记。pure-AI、单聊、group 分支的内容和角色处理不同。历史消息经过角色/群聊身份转换，用户 display name、群聊 roster/acting-as guardrail 被插入。代码路径包括 `_resolve_selected_persona`、`_resolve_session_system_prompt_mode`、`_build_group_api_messages` 等。
6. `prepare_conversation_with_worldbooks()` 根据 `worldbook_index` 获取全局/会话激活书，读取条目，按 scanDepth 扫描历史文本并执行用户正则匹配，生成插入消息；同时做 token 预算，调用 tokenizer 裁剪历史（`trim_messages_to_context` / `trim_assistant_openai_messages_to_context`）。知识图谱注入和 MVU/长期记忆则有独立路径/开关，不等于统一记忆流水线。
7. `prepare_llm_request()` 解析 preset、key、base URL、provider/protocol、auto resolution、effort/Fast、缓存控制块。`runtime.stream_chat_completions()` 走 `llm.registry.get_adapter()` 到 `providers/openai_compatible_chat.py`、`openai_responses.py`、`anthropic_messages.py`、`gemini_generate_content.py` 等 adapter；adapter 做请求/流事件映射。
8. provider stream chunks 被生成路由转成 SSE delta/reasoning/usage/meta/done；对断流、异常有 terminal error 路径。完成时 `_persist_generation_record()` 写 usage/generationMetadata、保存 chat，追加 usage ledger。写入是完整会话 JSON 写入，不是按消息 append。
9. 前端更新已创建的本地 assistant 消息，成功后常 reload authoritative chat；完成内容经 MessageList/Markdown 渲染。可选自动读消息由 TTS 播放 composable 管理，合成请求打到 `/api/tts/*`，音频通过 cache/audio endpoint；MVU daemon 可在消息后异步消费状态。

差异：group 用 `/generate/group`，按被选成员重复构造 member config/persona/角色约束及发言；interject 为 `/generate/interject` 单次插话；draft helper 是单独 prompt/流。regenerate/continue/swipe 主要在前端重用改消息/版本/分支动作再触发生成，消息版本也可能在前端保留为 greeting/assistant variant；不应假设每种都共用完全同一个后端 endpoint。工具调用包含 provider tool round-trip、工具结果消息/trace；助手 Agent 是独立 `/assistant` 路径及自身历史，不等于普通角色聊天默认自动调用一套工具。

**架构结论：**provider 适配器边界显式；业务 prompt 与生成生命周期仍由一个约 3,000 行级 `routes/generate.py` 主导，并且普通、群聊、插话有重复 prompt/context 组装。前端 `ChatPage.vue` 也保持编排中心。改 prompt 行为容易牵连多分支。

## 4. 数据模型与持久化

核心 schema 在 `backend/app/schemas.py`，大量 `extra="allow"` 保留扩展/旧字段；以版本字段/validator/读写时兼容逻辑处理，而非统一显式迁移框架。

| 实体 | 真实位置与引用 | schema / 写入 / 主要风险 |
|---|---|---|
| Character | `data/characters/{id}.json`；头像为 `data/avatars/` 文件；WorldBook 用 ID 引用 | `CharacterCard`，含人格、scenario、exampleDialogue、systemPrompt、regex、MVU 初始表；extra allow。全文件替换保存；未知字段保留但 schema 可漂移 |
| Chat/Conversation | `data/chats/{characterId}/{chatId}/chat.json`；旧格式兼容路径；path/fork 索引 JSON | `Chat` 含 messages 全列表、overrides、group members、fork refs、stateVariables。加载/保存完整对象；每次消息/元数据变化序列化整份聊天，O(消息总字节数) |
| Message | 内嵌 `Chat.messages[]` | `ChatMessage` 含角色/正文/图片引用/assistant variants/reasoning/tool trace/usage/generationMetadata/TTS 信息。多种 generation/legacy extra 共存，消息量大时单文件持续增长 |
| Settings | `data/settings.json`；API keys/provider config/OAuth 状态引用 | `Settings` 下 prompts、LLM presets、Personas、appearance、regex、TTS 等。仍有旧配置/新协议配置并存，保存整文件；OAuth token 独立 `data/oauth_tokens.json` |
| WorldBook | `data/worldbooks/{id}.json`；session/global 激活关系及 activation index | `WorldBook`→entries，globalActive/sessionChatIds；会话也以 overrides.worldBookIds 和 worldBookAttachments 双字段存在，由 validator 同步，属重复表示/兼容 |
| Persona | settings 的 personas 集合（`Persona` schema）由 session 的 `userPersonaId` 引用；消息保存 sender Persona/name/avatar 快照 | 切换后旧消息身份显示可保留；配置与消息快照存在重复身份数据 |
| Group | Chat 内 `isGroup/memberIds/memberSettings/groupDelay`，通过 character ID 引成员 | `GroupMemberSettings` 局部覆盖；成员 ID 与主 characterId 并存；UI/后端处理两端耦合 |
| TTS | 消息内 audio asset ID/source text；`data/tts_cache` 音频；settings 全局 preset + chat overrides.tts | cache、绑定、播放队列分离；会话仍含资产引用，文件清理/引用完整性需要巡检 |
| Assistant / tool | assistant 配置/对话各自 JSON；assistant workspace 文件系统；Tool state/trace 在消息或工具数据里 | 独立于 RP chat；权限确认状态部分在浏览器 localStorage；Agent 运行状态部分为内存/后台任务，重启行为不是持久 workflow |
| Memory | `chat_memory.json` 单独文件；KnowledgeGraph 为会话 `knowledge_graph.json`；MVU state 可在 chat 内嵌，日志单独 `mvu_logs.json` | `ChatOverrides.longTermMemory` 与 sidecar memory 重复用于兼容/运行时；摘要不是自动完整语义记忆；图谱/MVU 各有 schema |
| usage / OAuth / indexes | `usage_ledger.jsonl` append-only；OAuth tokens 单 JSON；chat/fork/worldbook 索引独立 JSON | JSONL 有增量 append 和去重缓存；索引可 rebuild；token/settings/chat 写入采用文件锁，`write_json` 写 `.tmp` 后 `os.replace` 原子替换 |

**强项事实：**`storage.py` 有 `portalocker` 文件锁、JSON 临时文件+原子 replace；关键 chat 写盘后同步索引。**风险推断：**chat、settings、character 多处全量重写，异常终止一般不会留下半个主 JSON，但会出现 `.tmp` 遗留、两份相关 sidecar 更新不在同一事务、并发读写的多实体不具备事务原子性。系统没有传统 DB migration log 之外的统一 schema migration registry；应用内兼容转换散在 schema validators、storage、settings/import-export。

## 5. Prompt 与上下文系统

- 形式是“生成路由中的 helper + 分支式构造器”，不是独立的可插拔 pipeline/middleware 对象。`generate.py` 中 prompt 拼接使用 `prompt_parts` 列表，条目之间用空行连接；worldbook/context 之后作为 API messages 插入。
- 字段包括全局 system prompt、Persona、角色卡 description/personality/scenario/systemPrompt、example dialogue、会话/runtime prompt、用户/角色占位符、group roster/acting-as guardrail、worldbook 注入、历史、可选 memory/KG/MVU 信息。不同会话模式可能改变 system role 放置及群聊身份包装。
- provider adapter 再将通用 `role/content/tool_calls` 转换为协议各自格式；这是目前相对明确的分层。
- Context 管理已经有 tokenizer service、已预热 DeepSeek tokenizer、模型 context size/budget 分配、消息裁剪及 worldbook token 预算；不等同于按需摘要历史的自动 summarization。自动长期记忆是助手总结机制/用户设置驱动，不是每次 generation 的统一压缩层。
- Worldbook 用激活索引减轻全库扫描；仍需扫描选中条目与有限历史窗口、执行 regex。regex 的灾难性耗时上限/执行隔离无法从当前审计确认为完整安全沙箱。
- Prompt cache 以 provider-specific generation config 适配，是上游缓存协议，不是本机完整 prompt KV 缓存。最近 `local_cache_hit_probe.py` 是“不打真实厂商”的本机命中探测工具，不代表已接入推理缓存。
- Prompt injection isolation/role leakage：group identity guardrail 与 role 转换存在；没有证据表明所有外部 WorldBook/角色文本被作为不可信数据隔离，也没有统一的强制角色泄露防护层。

最脆弱的三个点：① prompt 规则散落在多个 route 分支且重复；② 数据角色混合及 system/assistant/provider 专有差异使协议适配、上下文裁剪和 prompt 注入边界难以整体验证；③ 长期记忆、KG、MVU、WorldBook 是不同旁路，缺乏一个有预算/来源/信任级别的统一上下文计划。

## 6. 长会话能力

**已有缓解措施 FACT：**`MessageList.vue` 通过 `prefixHeights`、offset 查找和 `visibleMessages = messages.slice(windowStart, windowEnd+1)` 做可视窗口渲染/高度测量；流式文本经缓冲 patch；chat path/fork/worldbook 有索引；tokenizer/context 裁剪；write JSON 原子替换；history 有 context start marker 字段。

**已有成本迹象：**Chat schema 将全部 messages 嵌在一个 JSON，`load_chat` 每次解析全聊天，`save_chat` 每次序列化全聊天并替换整个文件；一次完整写入成本随消息体积线性增长。prompt/context 每次仍读取并遍历消息（虽然只在预算后发送部分历史）；WorldBook 对激活书/条目与选定扫描深度处理；所有消息文本本身可能较长。虚拟列表只减少 DOM，不减少 Pinia 持有全部数据、序列化或上下文处理。

- 复杂度：存储读写至少 O(N bytes)；渲染高度前缀计算随列表长度，更新时需看 `buildPrefixHeights` 缓存细节，无法仅凭 virtual window 断言滚动每步 O(log n) 全链路无成本；世界书匹配成本约与激活条目数×扫描消息文本量/regex 成本相关；build history 仍要转换至少被读取的历史对象。没有确认 O(n²) 必然热路径，不能把风险升级为已证实缺陷。
- tokenization：使用专用 tokenizer 且 generation 的 context preparation 有预算，具备明显保护；极长单条消息、未知 tokenizer 或模型 context size 配置缺失会影响估算/裁剪精度。
- streaming：SSE 增量缓冲降低高频 UI 更新；断流错误/停止的持久化分支存在。长时间浏览器后台/移动系统冻结可能中断 fetch/任务。
- TTS 队列：前端 queue 对可读文本播放；串行长 queue/页面生命周期/音频释放是需验证边界，本次未做 runtime soak。

结论：数百轮下 UI DOM 端已有实质优化，单文件全量 load/save 与 prompt 构建仍是主要可预见成本；成千上万轮及大量图片/长文本需真实性能数据验证。不要将“virtual list”误读成端到端虚拟化。

## 7. 移动端 / Android 可行性

现状证据：`index.html` 仅 viewport 元标签，无 manifest/service worker；`vite.config.ts` 默认端口 9081、API proxy `127.0.0.1:9091`；后端默认 CORS 只放本机 origin，扩 LAN 要显式环境变量；窄屏 composable 和拖动 FAB 等触控相关实现存在；消息虚拟列表可复用；聊天与状态仍驻留 Web 页面/浏览器内存。

- Responsive：存在 `useViewportNarrowPortrait`、多处窄屏 CSS/UI 调整，证明响应式不是零；但尚无独立 mobile navigation/workflow 或完整真机验证记录。
- Keyboard/scroll：输入组件以 textarea、页面滚动区和消息虚拟窗口工作；移动浏览器虚拟键盘改变 visual viewport、聚焦后 resize、scroll anchoring、底部 FAB/输入栏遮挡风险，需要针对 iOS/Android 浏览器验收。本次未运行设备验证。
- touch：存在浮动按钮拖动和 hover preference 抽象；复杂悬浮按钮/弹层菜单/hover affordance 会提高纯触屏适配成本。
- files/audio：文件选择器依赖浏览器 `<input type=file>`/File API，具备基础 web 兼容潜力；剪贴板富文本解析 endpoint 面向本机临时路径，移动设备路径语义不同。Web Audio/HTML audio 可播放，但 TTS 本地引擎需要后端机器 GPU/模型文件，移动浏览器不能自然控制手机原生后台合成。
- lifecycle/offline：无 service worker/offline cache；前台 SSE 需网络持续连接，页面进入后台可能被系统节流/冻结；无持久任务续传机制。localStorage/sessionStorage 有少量 UX 权限/临时态，但不是主数据仓储。
- backend/network/security：当前前端 default dev proxy 是 localhost 地址；生产资源由 preview/static server 提供，API 地址假设/部署变量需查 `frontend/src/api/http.ts` 与运行配置。后端可配 LAN CORS/bind，但无用户认证，远程 backend 暴露风险和多用户隔离不成立。SSE 为 HTTP stream，不见 WebSocket 聊天传输要求。
- WebGPU 是浏览器能力且需要安全上下文；LAN 的普通 HTTP IP 可能不可用，`webgpuProbe.ts` 明确提示 https/localhost 限制。Android device 对 WebGPU 支持随浏览器/GPU 变化，不能作为可靠基线。

三路线以现状估算：

| 路线 | 复用 | 必须处理 | 与当前结构的贴合度 |
|---|---|---|---|
| A Web UI + 远程 backend | Vue UI、REST/SSE、provider/runtime、JSON storage、聊天与数据 schema | API base URL 配置化、CORS/HTTPS、身份认证/授权、用户数据隔离、上传/文件/本地 TTS 能力语义、网络断线恢复和部署安全 | 最快共享现有代码，但后端缺少 auth/tenant 是显著产品安全阻碍；当作可信单用户私人服务器比公网产品自然 |
| B Capacitor/WebView + 远程 backend | 几乎所有 Vue 视图/API/SSE/chat runtime UI 可复用；WebView 可用原生文件选择/audio 插件 | API URL 配置和登录、安全的 token 存储、键盘/viewport/状态栏/back gesture、后台音频、下载/分享/附件桥、WebGPU降级、移动触屏重做与商店生命周期 | UI/runtime 分离仍未彻底，但改造范围可控；必须先让 API client 不把 localhost 当默认实际服务地址，并解决 remote backend trust boundary |
| C Android 本地 runtime/backend | 前端 UI、数据 schema、provider adapters 的业务概念可复用；部分 Python 核心无法直接运行在 Android WebView | Python/FastAPI运行方式/依赖/文件路径/锁/子进程/TTS模型、端口生命周期、模型文件体积、Android后台限制、native bridge、安装升级及本地 provider secret 管理均要重新工程化；async worker和系统级服务需改造 | 当前最不自然、成本最高；仓库把后端视为独立本机进程并使用桌面文件系统与可启动 TTS 子进程 |

事实导向判断：**B 的 UI 复用路径最直接**，A 技术改动少但产品安全/远程数据边界需补强；C 不只是打包 Web 页面，而是移植 Python runtime/存储/后台服务。

## 8. 当前产品能力盘点

| 功能 | 状态 | 关键实现位置 | 成熟度/已知限制 |
|---|---|---|---|
| Character creation/edit | Implemented | `CharacterEditorModal.vue`, `routes/characters.py`, `schemas.py` | JSON 卡片、字段多；schema extra allow |
| Character import | Implemented | `routes/import_export.py`, `frontend/src/components/modals/*Import*` | 含嵌入卡/PNG，带兼容与警告 |
| Chat import/export | Implemented | `routes/import_export.py`, ChatImport/Export modal | 支持多格式与 warning；规格核对仍是文档任务 |
| SillyTavern compatibility | Partial | backend `st_mvu_compat.py`, import routes、相关 converters | 多处兼容格式存在；不能据此称全量 ST 兼容 |
| JanitorAI import | Partial | `extensions/simpletavern-janitor-bridge/`, ChatPage pending handoff | 依赖浏览器扩展/网页桥接，非通用 API 同步 |
| WorldBook | Implemented | `schemas.py`, `routes/worldbooks.py`, `generate.py`, `worldbook_index.py` | 激活/扫描/正则/深度插入；处理成本随条目及扫描历史增长 |
| Regex transforms | Implemented | backend/frontend `content_regex*`, regex editor | 前后端路径并存；复杂用户表达式时性能/兼容性需留意 |
| Persona | Implemented | Settings schema、`PersonaEditorModal`, `ChatPage` | chat 引用 persona，消息存身份快照 |
| Model/provider settings | Implemented | `SettingsDrawer`, llm routes/catalog/preset resolve | 四类协议和 OAuth 已接入；目录与厂商差异快速演化 |
| Prompt configuration | Implemented | `SettingsDrawer`, `generate.py` | 覆盖层丰富，组装仍分散且会话模式复杂 |
| Streaming | Implemented | `routes/generate.py`, `api/sse.ts`, `useChatGeneration.ts` | SSE 有 meta/usage/error；实际连接仍受浏览器生命周期影响 |
| Regenerate/continue/swipe | Implemented | `ChatPage.vue`, `useMessageVersions.ts`, chats store | 多依赖页面内编排/消息版本语义；需黑盒覆盖组合场景 |
| Message edit/delete | Implemented | ChatPage、MessageEditorModal、chats routes/store | 删除后缀/重生成与索引持久化耦合 |
| Chat branching | Implemented | `chatFork.ts`, `routes/chats.py`, `fork_index.py` | lineage/index 已有优化，索引 rebuild 是额外复杂度 |
| TTS | Implemented | `/routes/tts.py`, `services/tts_platform.py`, queue composable | 平台与本地引擎并存，需后端资源；缓存与消息绑定 |
| Group chat | Implemented | `useGroupChat.ts`, Group modals, generate group/interject | 多成员 prompt/控制复杂；成员级参数已有 |
| Narrator | Partial | Group/generation role helpers and UI fields | narrator 专属流程成熟度/独立契约未确认，勿等同完整旁白引擎 |
| Assistant agent | Implemented | `services/assistant_agent.py`, `/routes/assistant.py`, Assistant tools | 独立会话与权限开关；不等于主 RP chat 的通用 agent runtime |
| Long-term memory | Partial | chat_memory storage, assistant summary flow, overrides | 手动/定时助手摘要和多套 memory 表示；无统一自动检索/压缩流水线 |
| Tool calling | Implemented | `llm/providers/*`, `assistant_tools/`, generate search round | 多协议工具适配；不同工具域权限/错误和状态各自有实现 |
| File operations | Partial | assistant workspace handlers, attachment policy, clipboard route | assistant 可操作 workspace；剪贴板本机临时路径假设限制移动/远程 |
| WebGPU effects | Experimental | `useWebGpuBackground*`, shader modal, presets route | 依赖安全上下文/GPU/WGSL；非跨设备必备能力 |
| Themes/appearance | Implemented | styles, settings store/drawer, background | Web UI 主题/背景配置已在；不是原生 Android 系统主题适配 |
| Mobile layout | Partial | `useViewportNarrowPortrait`, responsive CSS | 尚未 PWA、离线或可证实真机全流程 |
| Backup/export | Implemented | import/export routes, export modal | 文件型存储便于备份，但一致性/全量备份流程需运行核验 |
| OAuth sign-in | Implemented | `routes/oauth.py`, `llm/oauth/`, OAuth modal | Copilot/Codex flow；状态保存在后端本机 |
| PWA/offline install | Not Found | — | 未发现 manifest/service worker |
| Automated tests in repo | Not Found | Git commits removed Vitest/pytest | 以外部规格黑盒核对取代仓库内测试 |

## 9. 测试与工程健康

- 前端：Vue 3 + TypeScript，`npm run build` 执行 `vue-tsc -b && vite build`。本次执行失败，TypeScript 报 `frontend/src/views/ChatPage.vue` 重复对象属性 TS1117：行 2689、2757、2772、3573、3632、4300。Vite bundling 因前置类型检查未执行。
- 测试：HEAD 近期 `e36a351` 移除 Vitest，`8f94b81` 移除 pytest；文档 `docs/00-INDEX.md`/roadmap 明确仓库不含自动化测试并将测试放在仓库外。未发现 Playwright/E2E。coverage：无可用数据。
- Backend：`backend/requirements.txt` 为依赖入口；本次未启动服务或执行 import/运行验证。Python 服务依赖可用环境/venv 与数据目录，运行行为未经本次确认。
- Lint/typecheck：前端 build 已跑到 vue-tsc 并失败；未见独立 lint script。typecheck 当前失败。后端 lint/type checker 配置未确认。
- CI：仓库文件搜索未发现明确 `.github/workflows` CI 配置。不能据此断定托管平台绝无外部 CI。
- Packaging/deployment：有 deploy/update 脚本与后端 update route；未发现 Electron/Tauri 包装器、容器部署体系或 Android 包。
- 核心无测试保护：prompt/context、协议映射/流事件、storage migrations/atomic writes、长聊天 fork/分支、group/interject、工具安全边界、TTS、本地/远端 CORS 行为、import/export。规格文件提供人工对照锚点但不自动防回归。

## 10. 技术债与风险分级

| 等级 | 问题 | 证据 | 为什么重要 / 未来限制 |
|---|---|---|---|
| Critical | 当前前端源码构建不通过 | `npm run build` 6 处 TS1117，`ChatPage.vue` | 发布构建门槛未满足；当前 HEAD 可见静态构建失败，影响可复现交付 |
| Critical | 核心行为缺少仓库自动化测试 | 移除 Vitest/pytest 的 commit、docs 测试策略 | provider/prompt/storage/导入等重构缺少本地回归反馈；外部人工规格核对成本高 |
| High | 生成编排/prompt 集中且分支重复 | `backend/app/routes/generate.py` 中 stream/group/interject 三套约 1,000 行级区段 | 新 provider、上下文功能或安全规则需多处同步，差异易漂移 |
| High | 前端聊天编排中心过大 | `frontend/src/views/ChatPage.vue` 约 4,300+ 行且含群聊、状态、SSE、交互；本次 build 错误也在此处 | 页面状态耦合让移动端/功能重设和构建排障风险上升 |
| High | 远程部署缺认证/用户隔离 | FastAPI CORS/env 配置但未见 auth/tenant middleware；单用户 JSON root | LAN/互联网暴露不能提供个人云服务所需访问控制和数据隔离 |
| High | 全量 JSON chat 读取/重写 | `Chat.messages[]`; `load_chat`, `save_chat`, `write_json` | 长会话或多媒体元数据持续扩大每轮 I/O、序列化/锁占用，限制移动弱设备/多用户规模 |
| High | 源码、规格、交接状态的版本漂移 | `version.py=v0.810`；v0.820 commit/doc 已完成；`CURRENT.md` 将T-814视为剩余，但后续又开发 v0.810/v0.820 | 发布状态、测试策略和优先级不易一眼判断；需人工重新对照实际行为 |
| Medium | schema 宽松并夹杂兼容/重复字段 | `extra="allow"` 多实体；`worldBookIds`与attachments；longTermMemory 与 sidecar | 数据转换隐式，客户端/迁移可能留下未识别字段或重复状态冲突 |
| Medium | 前端存储边界不清晰 | 主数据由 API 文件后端管理，部分权限/偏好在 localStorage/sessionStorage | 迁移到跨设备/原生客户端时要决定哪种状态属用户数据、如何同步/清理 |
| Medium | Android/远端地址与设备生命周期未产品化 | Vite localhost proxy、无 PWA、SSE前台流、临时路径剪贴板、本地TTS子进程 | “随身”体验需网络/API/后台行为重新定义，单纯壳无法补齐 |
| Medium | 多资源写入缺跨文件事务 | chat + memory sidecar、chat + index 更新顺序分开 | 崩溃/并发时可能短时索引或引用不一致；有恢复索引和 integrity scan 但不是事务 |
| Medium | 复杂 prompt/regex 无自动性能/安全回归 | 用户 regex 扫描 history；无自动测试 | 长会话与恶意/昂贵规则的性能退化难及时发现 |

## 11. 文档与代码现实差异

- README 顶部宣称“v1.0 稳定化阶段”，但 `backend/app/version.py` 是 v0.810，当前 roadmap/backlog 仍列 T-814 未完成，T-832 未完成；这不是已发布 v1.0 的证据。
- README/规格声称 API/UI 控件覆盖规模（BACKEND-API 112 paths/137 operations；FRONTEND-FEATURES 654/当前任务状态另有 649），这是文档快照，实际交互/接口逐项黑盒核验尚未完成；版本数字不能代替运行测试。
- README 对移动布局、virtual message list、CORS、原子写等说明大体能在代码定位到对应实现；但响应式不等于 PWA/后台运行，virtual list 不等于数据虚拟化。
- v0.700 roadmap 一处称 `ChatPage`/`SettingsDrawer` 组件化已完成，同时保留不拆整个文件边界；实际 `ChatPage.vue` 仍为 4,300 行量级，若读者把“组件化完成”理解为页面编排解耦则不准确。
- v0.800 计划文档描述错误 envelope、性能 profiling、四协议、usage 等已完成；代码中相应模块确实存在。但 T-814 外部黑盒验证仍未做，因此“编码完成”并不等于规格逐项验收。
- roadmap 在 2026-09-11 把 v0.820 OAuth/member settings 标记落地，实际代码与 HEAD近期提交可证；但 app version 仍 v0.810、`CURRENT.md` 仍称尚未启动 v0.900/T-814 待执行，状态落后。
- v0.810 文档说“当前版本”，v0.820 又有完成提交与路线图。近期提交从 9/11 至 9/29 持续加入 Gemini 搜索、prompt cache probe、目录/参数等；文档状态页没有同步整个最新周期。
- README 将“本地单用户”等口径作为定位；配置可经 CORS/bind 远程连接，但缺身份认证，文档的“远程可访问”若有表述不应理解为远程多用户 ready。
- Git 9/20 提交明确将测试策略改为外部规格对照并删去测试框架；这与旧任务卡/过往测试命令可能冲突，当前策略以最新 `docs/00-INDEX.md`、roadmap 与提交为准。

## 12. Git 最近演化方向

近三个月可见历史高度集中在 2026-09-09 至 09-29（中间 8 月到 9 月有明显提交间隔，不能据最新几周外推每日开发强度）：

- 8 月初：原生协议与工具 round-trip、缓存、TTS/性能基础。
- 9 月初：provider catalog、特殊 auth、protocol auto resolution、提示缓存/模型控制台。
- 9/11：Copilot/Codex OAuth、群聊成员 reasoning/Fast。
- 9/20：usage/cost、search、性能/数据可靠性扫尾；新增人工黑盒规格并移除 pytest/Vitest。
- 9/29：静态审查修复、Gemini 搜索来源显式选择、本机缓存探测。

判断：项目处在**能力快速扩张后的工程收口/稳定化尝试中，但仍有新能力加入**，尚未稳定冻结。依据是最近主要工作仍增加厂商协议/目录/搜索/鉴权等，而同周期又整理规格、错误契约、性能与发布核验；build 失败与 T-814 未完成不支持“已稳定发布”。

## 13. 冻结新功能后的 1.0 距离

### Must fix before 1.0

- 修复并重新确认前端 production build 可成功（当前 TypeScript build 已失败）。
- 对核心产品路径完成一轮发布候选验证：启动/设置、导入角色/聊天、单聊流式、group/regenerate/fork、四 provider、错误/断流、TTS、备份恢复。文档中的 T-814 是合理的验收基线，但其实际范围需以当前实现校准。
- 明确发行版本与文档状态：README v1.0、运行版本 v0.810、v0.820 变更、CURRENT/backlog 的实际状态要收敛，确保下载/更新显示不误导。
- 对用户数据做真实备份与恢复演练，确认 chat/settings/avatars/WorldBooks/OAuth/memory/index/TTS 等数据的边界和恢复行为。

### Strongly recommended

- 至少建立一组不依赖外网真实凭据的核心回归核验（若坚持不留仓库内框架，需有可复现的外部执行记录/版本结果）；重点为 schema migration、生成请求适配、SSE terminal/error、原子写/索引 rebuild。
- 确定支持的部署安全边界：明确单机 localhost；若 LAN/远程支持则提供认证/访问控制或明确安全部署约束。
- 用长会话和真机窄屏做性能/可用性验收，记录限值与已知限制。

### Can wait for 1.1

- Bedrock Converse/eventstream、Mistral Conversations、Vertex Anthropic rawPredict（T-832）。
- PWA/离线、原生 Android、本地模型 runtime、多用户与跨设备同步。
- provider 插件 SDK、复杂记忆系统重构、非核心 WebGPU 扩展。

## 14. 最值得重新思考的五个边界

1. **生成引擎 vs HTTP route/UI**：现况 `generate.py` 承担 request validation 到 prompt/context/stream/persist；拆分前先提炼稳定的 generation request、context plan、event contract，避免继续复制分支。
2. **运行时 vs 客户端**：当前 UI 假设一个 FastAPI 服务持有个人数据和本机资源；移动/远端路线前应解耦 API base URL、认证、设备能力和 local-only 能力，并决定谁拥有配置/数据。
3. **存储接口 vs JSON 文件实现**：JSON 可读、可修复是产品特性，但 Chat 全量读取保存与跨文件 sidecar 已限制扩展；先界定一致性、增量写、备份、迁移契约，再谈数据库或分片。
4. **提示内容 vs 有来源/预算/信任的 context pipeline**：角色卡、Persona、世界书、记忆、KG、群聊标识现由多处 helper 拼接；抽象前先定义排序、预算、来源可见性、可信级别与协议投影。
5. **provider protocol adapter vs 产品能力**：协议层 adapter 已拆，但缓存/search/tools/OAuth/effort 等跨协议能力仍由 resolution/runtime/generate 多处协商；先定义通用能力和 provider capabilities 的契约，避免能力字段逐渐变成隐式厂商开关。

## 15. 作者 2～3 小时重新熟悉代码的阅读顺序

1. `README.md`：产品表面定位、启动/端口与用户路径；对照代码校验其版本口径。
2. `docs/01-ROADMAP.md`：版本目标和范围；标记哪些是计划状态而非验收结论。
3. `backend/app/main.py`：后端启动、路由、生命周期、CORS 和后台任务。
4. `backend/app/schemas.py`：关键实体真实字段、重复表示与 legacy validators。
5. `backend/app/storage.py`：数据目录、锁、原子 JSON 写、Chat 路径定位和 sidecar。
6. `frontend/src/main.ts` 与 `frontend/src/router/index.ts`：前端启动和页面路由。
7. `frontend/src/views/ChatPage.vue`：消息提交、单聊/群聊/重写/持久化的主页面编排。
8. `frontend/src/components/chat/ChatInput.vue`：用户输入与提交事件边界。
9. `frontend/src/composables/useChatGeneration.ts`：生成流状态、SSE 事件/错误/完成处理。
10. `frontend/src/api/sse.ts` 与 `frontend/src/api/http.ts`：浏览器到后端的实际传输和地址配置。
11. `frontend/src/stores/chats.ts`：客户端会话状态/消息 patch 模式。
12. `frontend/src/components/chat/MessageList.vue`：长会话虚拟列表和高度/滚动机制。
13. `backend/app/routes/generate.py`：完整服务端 prompt/context/group/stream 主干（建议分段读）。
14. `backend/app/tokenizer_service.py`：context token budget/cutoff 实现。
15. `backend/app/llm/resolution.py`：preset/provider/protocol/参数解析。
16. `backend/app/llm/runtime.py` 与 `registry.py`：业务到 provider adapter 的调用边界。
17. `backend/app/llm/providers/`：请求、响应、SSE、工具/usage 的协议变换。
18. `backend/app/services/assistant_agent.py`、`assistant_tools/`：助手与工具系统边界。
19. `backend/app/routes/tts.py`、`services/tts_platform.py`、前端 TTS queue：合成/缓存/播放的端到端状态。
20. `docs/specs/BACKEND-API.md`、`FRONTEND-FEATURES.md` 与 `docs/state/CURRENT.md`：人工验收面和状态漂移。

## 16. Executive Handoff

Simple Tavern 当前是一个面向单个可信用户的本地 AI 角色扮演工作台。用户通过 Vue 3 + TypeScript 浏览器 UI 管理角色卡、聊天、Persona、World Book、群聊、助手、工具、记忆和 TTS；本机 FastAPI 服务负责读写 JSON 文件、组装上下文并连接云端模型/搜索/TTS 服务。数据默认在本机，并非完整离线软件：推理通常依赖外部 API，部分搜索/TTS 也依赖第三方。仓库没有原生桌面壳、Android 客户端或 PWA/service worker；“桌面”实质上是浏览器前端加本地 Python 后端。

架构上，前端入口是 `frontend/src/main.ts`，聊天核心页面是 `ChatPage.vue`，状态在 Pinia stores，API/SSE 在 `frontend/src/api/` 和 `useChatGeneration.ts`。后端入口 `backend/app/main.py` 注册 FastAPI routes；存储中心 `backend/app/storage.py` 使用按实体组织的 JSON 文件、portalocker 锁和临时文件原子替换。协议层已有清楚的 provider adapter：OpenAI-compatible、OpenAI Responses、Anthropic Messages、Gemini 等经 registry/runtime 调用。真实架构中心仍是 `backend/app/routes/generate.py`：普通聊天、群聊、插话、prompt 拼接、历史裁剪、WorldBook 注入、provider 调度、SSE 和持久化都在这一区域；前端 `ChatPage.vue` 也承担大量聊天编排。

成熟度较高的能力包括角色/聊天/世界书导入管理、单聊流式生成、群聊、消息操作与分叉、四类模型协议、OAuth 登录、usage/cost 记录、助手工具、TTS、多类错误/数据完整性处理。长列表有虚拟窗口，生成上下文使用 tokenizer 与预算裁剪；文件写入有锁和原子替换。这些是有代码证据的工程基础，但不代表经过完整发布验收。

当前明显未完成的部分是发布状态收口与端到端验证：本次 `npm run build` 在 `ChatPage.vue` 六处 TS1117 重复对象键报错，build 未成功；Git 记录 9/20 移除了 pytest/Vitest，文档明确自动化测试不在仓库内，核心功能缺少本地回归保护。路线图 T-814 黑盒规格核对仍未完成，T-832 额外协议仍排在 P1。版本事实也有漂移：README 写 v1.0 稳定化，`backend/app/version.py` 仍是 v0.810，代码/roadmap 已包含 v0.820 OAuth 与群聊成员参数。

最大的架构问题是业务生成流程与 UI 编排分别集中在巨型模块；provider adapter 虽然解耦，但 prompt、上下文、工具/搜索以及持久化策略尚未形成独立的 generation engine/context plan 契约。其次，数据模型采用宽松 Pydantic schema 和大量 JSON 全量读写/兼容字段；这有利于透明与修复，却让长聊天写入持续变重，且跨 chat/memory/index 无事务。远程访问配置存在，但没有用户认证/tenant 隔离，当前不应理解为安全的多用户服务。

移动端最大阻碍不是屏幕 CSS，而是产品运行模型：UI 默认依赖一个服务端地址；后端负责文件系统、剪贴板临时路径、本地 TTS 子进程和 OAuth token；无 PWA/offline、无后台任务续传，前台 SSE 易受浏览器生命周期影响，LAN HTTP 下 WebGPU 也可能受安全上下文限制。现有窄屏布局、Vue UI、REST/SSE、数据 schema 和 provider runtime 可以复用。Web UI 加远程 backend 或 Capacitor shell 是更贴近当前结构的路线，但远程认证、URL 配置、音频/键盘/文件体验必须补齐；把 Python/FastAPI 核心移到 Android 本地则是最高成本路线。

若冻结新功能，可信 1.0 前至少要让 production build 通过、完成当前代码与接口/UI规格的实际核对、做备份恢复演练、对齐 version/README/状态交接，并明确支持的部署安全边界。PWA、原生 Android、多用户云服务、provider 插件 SDK 和复杂记忆重构可以后置到 1.1 或方向决策之后。

下一阶段最值得作者亲自决策的问题：①产品是否继续限定为本机单用户，还是要支持远程设备连接；②核心数据的 JSON 可读性与长会话增量/一致性如何平衡；③是否先拆 generation engine/context pipeline，或继续以 route helper 快速加协议；④移动端首选远程服务+WebView 还是未来本地 runtime；⑤无仓库自动化测试的前提下，谁负责、如何复现发布验收及回归记录。

