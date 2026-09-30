# Android 原生客户端与跨端独立主机：可行性调查

调查日期：2026-09-29（Asia/Hong_Kong）  
基线：当前 master 工作树；PROJECT_STATE.md 是调查入口，不视为无需核实的事实。  
范围：技术调查与决策准备。本轮只新增本报告；未修改业务源码、依赖、真实数据或 Git 历史。

## 1. 决策摘要

**有条件首选：先保留 Python 为唯一业务核心，将单聊生成和存储从 FastAPI route 抽为可直接调用的应用服务；Android 原生 UI 进程内调用此 service，桌面 FastAPI/Vue 继续调用同一 service。LAN 开关只启停远端 HTTP listener 与 Vue 静态资源，不是手机本机聊天的依赖。**这最大限度复用当前 prompt、provider、文件数据和 schema 行为，也符合“谁是 host，谁持有数据并执行生成”。

这是一个需先过纵向实验的路线，不是 Android 兼容性已验证。当前直接依赖的 Pydantic v2 Rust 扩展和 tokenizers>=0.15 是首要打包风险。本轮查到 Chaquopy 17 官方支持 Python 3.10–3.14、minSdk 24；其官方 Android wheel 索引可见 tokenizers 0.7.0/0.10.3，低于仓库要求。没有确认到可直接安装的 pydantic-core 当前 Android wheel。本环境无 Android SDK/adb，也未做 Android build 或真机验证。官方资料：[Chaquopy 17 Android 文档](https://chaquo.com/chaquopy/doc/current/android.html)、[版本表](https://chaquo.com/chaquopy/doc/current/versions.html)、[tokenizers Android wheel 索引](https://chaquo.com/pypi-13.1/tokenizers/)（2026-09-29 查询）。

**备选路线：**如果关键 native wheels 不可维护，或 Python runtime/后台生命周期不能满足目标设备，再评估 Kotlin/JVM 共享核心。它可以让 Android 原生 UI 与桌面 host 共用领域实现，但须迁移现有 Python prompt/context/provider/storage 行为；现阶段不是轻量改造。Python/FastAPI 可先留作桌面兼容 API adapter。

**不建议长期采用 Android 单独重写、桌面保留 Python。**它可较快得到原生 demo，却会双实现 prompt/预算裁剪、provider event、消息版本、分支、保存及群聊调度。共享 JSON schema/API 只能减少字段漂移，不能消除业务逻辑复制。

当前生成核心集中于 backend/app/routes/generate.py：读角色/Persona/settings/history/WorldBook、构造 prompt 与预算裁剪、请求 provider、SSE、保存消息及 usage。另一方面，群聊概率筛人、成员顺序循环、delay、暂停与待续成员在 Vue ChatPage/useGroupChat，尚不是 host task。原生端若直接复用现有 endpoints，仍要复制这些规则、版本管理、并发防护与部分取消后保存行为。

**MVP 应承诺：**client disconnect 后 host generation 继续、重连后可读取已保存结果；若主机进程被杀，显示 interrupted 并保留已存消息。先不承诺恢复每个 delta、杀进程后自动恢复任务，或续跑 provider 的同一次生成。

## 2. 当前代码与目标的差距

| 目标 | 当前事实 | 差距 |
|---|---|---|
| Android 原生且本机独立聊天 | 未发现 Android 工程、Gradle/Manifest、原生 UI；Python 后端持有数据和执行生成 | 尚未实现；需 core facade、Android host 和原生 UI |
| 本机数据、context、provider 与保存 | storage 使用文件路径、Pydantic、锁和原子替换；generate route 管理生成 | 可复用规则，但目录要映射到 app 私有区，存储锁/替换需 Android 验证 |
| 可选 LAN Vue | 后端已有 FastAPI 与可配置 CORS/bind；Vite preview 可配置 host | 没有产品化共享开关、配对、Vue dist 同源 host；默认 app.main 示例绑定 127.0.0.1 |
| 桌面继续独立运行 | Python + Vue 启动路径已有 | 可以继续；LAN 开关需正式进入 desktop host |
| 手机与 Vue 共享核心 | Provider adapter 在 Python 后端共享；群聊调度及部分版本状态在 Vue | 只部分共享，需把领域用例/task 状态搬至 core |
| 本机聊天不依赖共享 | 当前 UI 依赖 HTTP API；无 Android 本机 service调用路径 | 需新增进程内调用；共享关闭时不监听 LAN |

证据锚点：backend/app/main.py:37-71,96-141,197-224；backend/app/storage.py:87-110,576-592,1736-1806；frontend/vite.config.ts:4-27；backend/app/schemas.py:1024-1125,1425-1480。

证据强弱：代码事实由本轮源码检查确认；Android 平台要求来自 2026-09-29 官方资料；运行时结论有限，因为仓库 venv 无法启动且本机无 Android SDK。推断会标明；未实测事项列为未知。

## 3. 聊天核心的最小闭包

### 3.1 单聊调用链

1. ChatPage.vue 的 sendUserMessage（约 2515 行）接收 ChatInput，检查 isGenerating，flush 问候版本变更、替换输入占位符、上传图片、创建 UI 临时消息；请求 POST /api/generate/stream。
2. generate_stream（generate.py:1294）load_chat、load_settings、load_character，解析 pure-AI/session/persona；必要时 ensure_mvu_worker。按默认 appendUserMessage 在流生成前把 user message 加入 chat 并 save_chat（约 1365 行）。
3. Prompt 依模式拼接 global system prompt、会话 Persona、角色名/personality/scenario/exampleDialogue/systemPrompt、长期记忆、chat override prompt 与 runtime prompt，并替换占位符。persona 优先使用本次请求带来的 persona snapshot，再回退到 chat/settings 所选 persona。
4. chat history 投影为 provider messages，执行 contextStartMessageId 锚点；prepare_conversation_with_worldbooks（generate.py:1008）按激活索引/条目 order/触发词/regex/scan depth 注入 WorldBook；tokenizer 按 context budget 裁剪历史。长记忆存 sidecar，KG/MVU 是旁路能力，不是统一的自动记忆流水线。
5. prepare_llm_request/_prepare_generation 决定 preset/key/base URL/provider/protocol、模型参数优先级与可选 cache/search/tools。llm.runtime.stream_chat_completions 经 registry 到 OpenAI-compatible、Responses、Anthropic、Gemini adapters；adapter 解析 SSE/协议事件、reasoning、usage、tool call。
6. route 将事件转为 meta/delta/reasoning/usage/done/error。成功后 _persist_generation_record（generate.py:224）写 assistant 内容和 generationMetadata、保存完整 chat、记 usage 并通知 MVU。异常发 terminal error。用户消息已先保存；assistant partial 在每个错误/取消分支是否写盘需逐分支运行验证，不能笼统承诺。
7. api/sse.ts 通过 fetch/ReadableStream 解码；useChatGeneration 持 AbortController 与停止标记；useStreamOutput 缓冲 delta 后 patch Pinia。完成后 reload authoritative chat。客户端主动停止时另有将本地 partial 保存的页面流程。

数据包括：characters/{id}.json；Persona、presets/settings 在 settings；Chat 包含全量 messages、overrides、persona、上下文锚点、媒体和群聊设置；WorldBook 单独 JSON；memory sidecar；MVU/KG/usage 有旁路数据。Chat.overrides.longTermMemory 兼容字段会在 save_chat 时移入单独记忆存储。

调用链证据索引：单聊 generate_stream 在 backend/app/routes/generate.py:1294，Persona resolve 在 423，worldbook/context helper 在 1008，保存元数据在 224；群聊和 interject handler 在 2038/2603。群聊 Vue 循环/发送位于 frontend/src/views/ChatPage.vue:2376,2515,2813,2865,2918；成员概率、暂停与待发状态位于 frontend/src/composables/useGroupChat.ts:46-184。流解码为 frontend/src/api/sse.ts:103，取消状态在 frontend/src/composables/useChatGeneration.ts:37-43。可按这些符号复查上面的事实。

### 3.2 一轮群聊调用链

它当前不是一个服务端 round task。ChatPage.vue startNextRound/continueGroupChat 与 useGroupChat.ts:46-204 持有轮次状态；Vue 从 chat.memberIds 按顺序取成员，用 memberSettings.probability 在客户端 Math.random 筛选，全被跳过时随机留一人；每人之间等待 groupDelay；逐人调用 /api/generate/group。后端重新读 chat/settings/该成员 Character，套成员 model/preset/temperature/top-p/reasoning/focus 参数、persona/角色条件、group roster 与 acting-as guardrail，组装 history/WorldBook/context并独立调用 provider。每个成功成员在该成员生成结束后保存。

成员列表、probability、memberSettings、groupDelay 在 Chat；实际这一轮的随机序列、currentSpeakerIndex、isPaused、pendingMembers 在 Vue 内存。暂停标志只在成员间/等待后由循环检查，当前 provider 请求不被服务端 pause task 管理。continue 用内存数组重新调度。插话通过 /api/generate/interject 单次请求；插话状态及暂停中用户输入顺序也在页面。界面关闭时已保存的成员结果仍可读，但待发队列/计划和 pause 进度丢失。

**禁言现状：**本轮在 Chat、GroupMemberSettings、生成请求及 Vue 群聊 UI中未找到独立 muted/banned 字段或禁言 API。已有成员 probability=0可让常规轮次概率筛选排除成员，但这不是独立禁言语义，也不阻止用户点成员头像走 interject。若产品要求禁言，需新增一个host存储的成员状态并让轮次与插话入口共同执行。

### 3.3 Vue 中的业务规则及迁移边界

| 行为 | 当前所在位置 | 状态持有者 | 界面消失后 | 是否迁入核心 | 最小迁移边界 |
|---|---|---|---|---|---|
| 单聊并发阻止 | ChatPage/useChatGeneration | Vue memory | 丢失；服务端没有任务状态 | 是 | core 按 chat 串行化 task；UI 保留按钮防重复 |
| delta buffer/打字效果/滚动 | useStreamOutput/Pinia/MessageList | Vue memory | 丢失；最终成功内容由 host 保存 | buffer/滚动留 UI；稳定task event入core | task event id/sequence/messageId，保存后可snapshot |
| Persona、placeholder、pure-AI身份 | generate.py helpers + 页面组请求 | chat/settings/request snapshot | 持久设置仍在host；临时输入随请求消失 | 是 | GenerationCommand的身份快照/优先级统一 |
| 消息 swipe 版本 | useMessageVersions.ts | 一般 versions/index/reasoning map在composable；greeting特例部分在ChatMessage | 临时版本丢；greeting字段保存 | 是 | message ID + version ID + activeVersion + content/metadata API |
| regenerate/continue | ChatPage；编辑/截断API后触发stream | Chat message + 页面多步状态 | 已写内容保留；任务操作状态不可查询 | 是 | 一个server command对targetMessageId与截断/替换语义原子处理 |
| 群聊筛选、排序、delay | useGroupChat + ChatPage | 配置在Chat；本轮执行在Vue memory | 已完成成员结果留存，计划丢失 | 纳入群聊时是 | GroupRoundTask记录筛选后成员序列/当前index/state |
| pause/resume/current speaker | useGroupChat + ChatPage | Vue refs | 当前/下一成员进度丢失 | 是 | host pause/resume/cancel API；MVP可只成员边界暂停 |
| interject与暂停期间插入用户消息 | ChatPage/useGroupChat | Vue状态 + 已存消息 | 消息留存；in-progress状态丢 | 是 | core对chat/task写入串行化 |
| TTS播放队列/Audio pause | useTtsPlaybackQueue | 浏览器Audio | 停止播放；文本历史不受影响 | 否（非聊天生成） | Native Audio adapter；host合成可另有task |
| 输入草稿、滚动、modal/search cursor | ChatPage/components | UI内存/local UI state | UI状态丢 | 否 | 仅UI层，除非另定义草稿持久化 |
| 保存版本再发送顺序 | ChatPage.flushPendingGreetingVersion | 页面操作顺序 + chat API | 关闭时可能没flush | 保存语义要迁 | active version变更须host持久化，生成按持久状态读取 |

直接复用现有 API 的 Android UI仍需复制：client lock、版本map与临时ID、regenerate的edit/truncate顺序、群聊scheduler/pause queue、失败partial的前端保存、task状态处理。单纯共用DTO不够。

## 4. Python / Android 依赖兼容矩阵

requirements：fastapi>=0.110、uvicorn[standard]>=0.27、httpx>=0.25、portalocker>=2.8、pydantic>=2.6、jsonschema>=4.20、python-multipart>=0.0.6、tokenizers>=0.15。

工作树 venv 元数据显示 CPython 3.12 Windows 安装，含 pydantic_core、tokenizers、httptools、watchfiles 等 Windows .pyd 扩展。其 python launcher指向缺失的系统路径，未能启动。此为文件元数据，不是 Android import 验证。

| 依赖/能力 | 代码用途 | 单聊必需 | Android证据 | 分类/验证 |
|---|---|---:|---|---|
| Python runtime | 全业务 | 是（路线1） | Chaquopy 17支持Python 3.10–3.14，minSdk 24；支持arm64-v8a、x86_64，ABI增加数MB及native依赖体积 | 候选，未验证本仓库闭包；先建最小app测包体/启动/RSS |
| FastAPI/Starlette | HTTP routes/schema/SSE | 本机直调不必；LAN Vue需要API adapter | 基础代码偏Python；Android listener与task lifecycle须实测 | 需适配；core直接调用，LAN才起listener |
| Uvicorn[standard] | ASGI server，standard带httptools/watchfiles等 | 本机不必；LAN需要server | 工作树原生模块为Windows ABI；当前Chaquo Android wheels未确认 | 需适配；尝试无standard依赖，或Android原生server adapter |
| HTTPX/anyio/httpcore | provider请求和流 | 是 | 主要Python实现推断可移植；TLS CA、异步cancel、响应流未知 | 需适配/验证；mock SSE测UTF-8分块、异常、cancel、TLS |
| Pydantic v2 / pydantic-core | schema验证、序列化、storage | 当前实现必需 | pydantic-core是Rust extension；未确认当前Chaquo Android wheel，历史issue记录过编译问题但不是兼容清单 | **主要风险/潜在阻塞**；对当前Python/API/ABI执行精确安装与构建 |
| tokenizers>=0.15 | DeepSeek tokenizer计数/context裁剪，启动warmup | 基本生成非硬依赖；context budget精确裁剪依赖它 | 官方索引只显示0.7.0、0.10.3 Android wheel，均低于requirement | **当前精确依赖闭包不可直接复用**；不是单聊启动/请求的硬阻塞：tokenizer lazy-load失败会返回 unavailable，context裁剪会退回不裁历史并留warning，长会话可能超出模型budget。尝试安装/新ABI wheel或替换实现，并测prompt差异 |
| jsonschema | assistant tool schema校验 | 默认普通单聊否 | Python层可移植推断，未试Chaquo | MVP可禁用；核对是否从全局import变强依赖 |
| portalocker | storage文件锁 | 当前store是 | Android lock backend未验证；可抽单进程/跨进程锁适配 | 需适配；多线程/多进程写和强杀恢复验证 |
| pathlib、tempfile、os.replace | 文件定位、临时写、atomic replace | 当前storage是 | app-private文件读写可行的推断；rename/fsync/Content URI行为需真机 | 需适配；root注入到filesDir、document URI导入导出 |
| asyncio/tasks/threads | provider stream、lifespan、MVU、scanner、后台巡检 | async provider是；很多任务可选 | Python/JVM线程生命周期未知；不可挂UI线程 | 需适配；独立worker/event loop，Service停机管理取消 |
| subprocess/signal | 更新器、本地TTS进程 | 否 | 本地TTS含Windows CREATE_NEW_CONSOLE，桌面更新器启动子进程；Android app sandbox不同 | 可禁用/平台替代；Core-only import与关闭流程探针 |
| OAuth/browser callback | OAuth routes、token store、localhost:1455 | 否 | Android browser intent/deep link流程与现有localhost回调未验证 | 后置；MVP先用API key，单独验证PKCE |
| TTS/local model/search/tools | optional services | 否 | process、GPU、权限/后台负担各异 | 能力可禁用或平台adapter，不阻塞文字聊天 |
| 剪贴板/桌面文件 | clipboard route使用temp目录、本地图片文件；workspace tools本机路径 | 否 | scoped storage与Android剪贴板/URI不同 | platform adapter；文件导入用SAF/Photo Picker |

main.py 当前top-level import很广：clipboard/update/assistant/TTS等路由均注册；lifespan做tokenizer warmup、索引预热、integrity scan、cache patrol、http log sweeper，shutdown又stop本地TTS子进程（main.py:39-71,96-130）。这是当前整个app的启动闭包，而不全是聊天必须。禁用TTS子进程不是“聊天核心不能迁移”的证据。真正需要优先验证的是Pydantic schema闭包、storage与HTTP provider；tokenizers是现有context-budget语义的打包阻塞/降级点，不是进程启动硬依赖。

**Android官方资料**（查询2026-09-29）：[Chaquopy 17版本表](https://chaquo.com/chaquopy/doc/current/versions.html)、[Android配置/ABI](https://chaquo.com/chaquopy/doc/current/android.html)、[官方tokenizers wheel目录](https://chaquo.com/pypi-13.1/tokenizers/)。索引目前只显示0.7.0和0.10.3。没有在此环境实际运行Android resolver；pydantic-core的其他wheel/自建可能性仍是未知，不作“绝对无法运行”结论。

## 5. 运行方案比较

| 维度 | 1. Python内嵌 | 2. 迁移共享Kotlin/JVM核心 | 3. Android独立重写 |
|---|---|---|---|
| 可保留 | 大部分Python prompt/context/provider/storage/schema理论上不动；FastAPI仅作桌面及LAN adapter | Vue/API transport、JSON fixture可留；Python domain需逐块迁至Kotlin，Python可暂作桌面adapter | Desktop Vue+Python照旧；Android新建全部规则 |
| UI调用 | Kotlin→进程内Python bridge；worker thread/async loop产Task event | Kotlin UI直调应用service/coroutine flow | Kotlin UI直调Android core |
| Vue LAN | 启动可选ASGI listener+dist host，和Native调用同一个Python service | 桌面/Android host暴露HTTP+SSE与Vue dist，直调Kotlin core | Android另写HTTP server；桌面仍Python行为 |
| HTTP是否常驻 | Native本机聊天不需要；共享开启时需要 | 本机不需；共享开启时需要 | 本机不需；共享开启时需要 |
| 打包与内存 | interpreter+native wheels，每ABI加体积；Python warmup/索引启动与RSS要实测 | 原生/JVM app可能省Python扩展，但迁移/desktop JVM host有成本 | APK易控，行为/回归双份 |
| lifecycle | Python task由Android Service托管，不可只靠Activity；桥接与Python loop管理困难点 | Kotlin task仍需Service，但Android工具链与共享JVM结构自然些 | Kotlin task可原生做，逻辑两份 |
| 数据兼容 | 最容易沿用extra allow、旧字段与JSON文件；路径/锁要adapter | 必须逐字段保证serializer/旧schema，并让桌面Python和Kotlin共存期间遵约 | 两端分别处理未知字段和migration，容易互相覆盖/丢字段 |
| 调试升级 | Chaquo/Python/Gradle/ABI联调；用户app升级时需数据migration | Kotlin/JVM工具完善；Python兼容桥需阶段性维护 | 单端调试简单，长期双端修复/QA最高 |
| 最大未知 | wheels、启动/RSS、后台、文件锁、LAN listener | 迁移实际面、旧Python和新核心兼容复杂度 | 行为差异累积的维护成本 |
| 判断 | **首选实验，条件通过才继续** | **备选路线**，关键依赖/生命周期失败则升级评估 | 短期demo对照，不建议长期架构 |

方案2先选Kotlin/JVM，是因为原生Android必须用平台UI，而它能让业务实现用于Android与桌面JVM host；不表示现有业务已适合Kotlin，也不主张全面重写。逐用例迁移须有现有Python行为对照。共享协议/schema和共享业务实现不同：前者共享字段/HTTP shape，后者共用负责prompt、调度与保存规则的同一domain实现。

**选择触发条件：**路线1要求精确Pydantic闭包可安装、mock流与取消正常、目标手机启动/RSS可接受、私有文件持久化可靠、LAN listener在合法Android生命周期内可用。tokenizers可有替代，但必须保留可接受的context裁剪行为；若只能关闭预算裁剪且长会话风险不可接受，或长期维护自编Rust wheels不合算，再评估路线2。若失败的只是可选TTS/Assistant，就禁用能力而不迁核心。没有设备指标与实测，不提供工期估算。

## 6. 核心、API与长会话接口

分层建议：

Native UI → 本机 Application Core → ContextPlan / Provider Runtime / Repository  
LAN Vue —（共享开启时 HTTP/SSE）→ 同一 Core  
Desktop Vue → Desktop FastAPI adapter → 同一 Core

统一命令：StartGeneration(chatId, clientRequestId, mode, input, targetMessageId, options)，返回generationTaskId。核心提供task状态、cancel、subscribe(taskId, afterSequence)、chat snapshot、message page。事件含sequence/taskId/messageId/type；成功消息先落盘再报completed。以每chat串行或显式409定义并发；同clientRequestId幂等。推荐revision/ETag/If-Match阻止旧Chat对象覆盖新数据。

当前接口：

- GET /api/chats/{id} 返回完整Chat，包括所有messages；storage.load_chat解析全文件。
- /chats 与 /chats/groups 有summary=true侧栏摘要；/chats/{id}/search可返回messageId/index/snippet，但不能按窗口加载历史。
- 修改/删除按message ID；ChatMessage有稳定id；fork lineage保存源chat/message引用。
- SSE是一条POST响应；客户端fetch reader解增量，无任务status、event replay cursor。成功结束后全量Chat reload；写盘是全量JSON替换。
- variants不是统一持久实体：一般版本数组/index在useMessageVersions composable的内存Map；greeting variants仅部分落message字段。regenerate由页面组合编辑/截断/再生成。
- 文件锁避免写文件互相撕裂，不是条件写；两个客户端可交错load→modify→save，产生后写覆盖先写。前端isGenerating只保护本tab，不保护重复HTTP或多端并发。

接口源码索引：backend/app/routes/chats.py:442/462 有 summary 模式；952 的 get_chat 返回完整Chat；972 的 search；1008 的 update_chat；1124/1200 更新/删除 message；1235 保存并截断。storage.py:1736 load_chat 和 1776 save_chat。message/schema锚点为 backend/app/schemas.py:1024,1425,1692,1758,1788；前端版本映射在 useMessageVersions.ts:41-51。

最小新增接口顺序：

1. 任务ID、幂等clientRequestId、状态查询、cancel、清晰task状态。
2. 稳定message/version ID，active version与regenerate/continue/truncate语义由host一次完成；chat revision/条件写。
3. 长历史按beforeMessageId/afterMessageId + limit分页；先量传输/解析成本，不先换数据库。
4. task sequence与短事件重放可后置。MVP可先客户端重连取snapshot及最终保存内容；不承诺完整逐delta resume。
5. 群聊进入时才做持久GroupRoundTask，含筛选后成员顺序、当前成员、pause/resume state。

四种成本分开判断：virtual list只改善UI渲染；分页改善网络传输；context budget/tokenizer影响prompt；JSON全量读写影响存储/序列化。Native UI不自动改善后三者。先量chat bytes、加载/保存耗时、首delta、RSS，再评估SQLite或消息分片。

## 7. 生命周期与恢复承诺

当前前端有AbortController；后端没有generation task registry/status/reconnect endpoint，generate.py无request.is_disconnected管理后台任务。ASGI stream cancellation后provider具体取消时点需要运行验证。异常事件会返回，但进程退出会失去asyncio task与provider socket。

| 情景 | 当前行为/未知 | MVP建议 |
|---|---|---|
| Android本机UI切后台 | 无Android宿主，未知；普通Activity进程不保证存活 | 要后台继续就由用户启动有通知的FGS/Service托管；否则明确前台离开时best effort停止 |
| LAN网页关闭/断网 | 浏览器fetch流断；server task会否继续未验证且没有task状态接口 | server-owned task与连接解耦；客户端断开不cancel |
| 手机锁屏 | 无设备验证，不能推断SSE后台可用 | FGS通知、锁屏与Doze/厂商ROM真测；不承诺所有设备无限运行 |
| host进程被杀 | 内存task/provider连接消失；无journal恢复 | 启动标interrupted；保留已保存user/assistant结果，提供用户显式重试 |
| 客户端重连 | 当前只能重新拉完整chat，无任务/事件重连API | task snapshot；完成取message，运行中可订阅新sequence；先不保证delta历史 |
| 群聊部分完成 | 成员成功逐个保存；余下队列保存在Vue | 后端task记录计划与index后才能承诺继续；否则初期禁用群聊或仅前台 |
| 重复点击发送 | 单窗口isGenerating拦截，服务端无幂等任务登记 | clientRequestId幂等 + 每chat冲突控制 |

不要混称“断线续传”：a 客户端断连后host任务继续；b 重连获取已保存结果；c 恢复delta事件；d host被杀后恢复任务；e provider恢复同一次generation。MVP目标a+b；重启最多保留已写结果并标interrupted，不承诺c/d/e。

Android官方说明（2026-09-29）：[FGS overview](https://developer.android.com/develop/background-work/services/fgs)、[后台启动限制](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)、[Android 15行为变化](https://developer.android.com/about/versions/15/behavior-changes-15)。FGS需用户可见通知，启动受target SDK限制；API35的dataSync类型有累计时间限制，不应未经核准将模型生成任务塞入该类型。具体service type按正式任务和当前政策再核准。

## 8. 双端局域网共享

### Listener与静态资源

- 共享关闭：Android UI直接调core，不开外网卡listener；本机loopback bridge若使用只作为进程IPC。LAN开关关闭不取消generation。
- 共享开启：Android host启动局域网listener；desktop host以正式开关替换手动bind/CORS设置。Android服务须有常驻通知；关闭listener拒绝新远端连接，不等价于取消task。
- 后端目前未发现StaticFiles mount frontend/dist。正式host需API优先路由、Vue dist static root/history fallback、资源hash、版本随app发布更新。Vite dev proxy到127.0.0.1不是手机安装后的静态host验证。
- Vue大多数调用是根相对/api/...，生成是POST fetch SSE；头像、图片、背景、audio也走相对资源路径。正式打包要实测所有资源、SSE、MIME/history fallback同源工作。
- 读取局域网IP需处理Wi-Fi换网/address变化，更新二维码；端口占用显式错误/让用户选择端口。当前无自动发现要求；MVP二维码只含host地址及短期配对入口。

### 配对、安全与Android网络限制

建议默认关闭LAN、用户主动开；随机短期pair code经确认换为可撤销bearer/session token，token不放公开bundle或长期URL query；给访问列表/全撤销。访客默认可聊天，不默认读API/OAuth secrets、升级器、工具workspace或危险管理接口；审Settings响应中敏感字段是否redact。当前设计是单host单用户，不需要租户。

当前CORS默认allowlist是loopback Vue origin，额外origin由环境变量；allow_credentials=False。CORS不是认证，不授权，也不能独立阻止所有跨站请求或local-network attack。共享应采用同源Vue/API，敏感接口要求配对token并校验Origin/Host；远端访问控制不能靠CORS。

Android local network：官方[权限说明](https://developer.android.com/privacy-and-security/local-network-permission)及[Android 17变化](https://developer.android.com/about/versions/17/behavior-changes-17)（查询2026-09-29）称Android 16 target 36为opt-in阶段，target 37+ Android 17要求ACCESS_LOCAL_NETWORK运行时权限；连接及接受TCP均在影响范围。发行target SDK时需复核最新要求。MVP不做自动发现，手动二维码但仍要处理权限。

### HTTP、HTTPS与设备生命周期

局域网HTTP下相对fetch/SSE/图片/audio有望可用，但需目标浏览器实测；WebGPU、Service Worker等依赖secure context，不进入共享MVP假设。HTTP私网访问的新浏览器permission/private-network策略也必须在实际Chrome版本测试。[MDN Secure Contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)、[WebGPU](https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API)（2026-09-29 查询）。

Android原生HTTP client的cleartext policy与PC浏览器网页政策不是同一层。[Android cleartext文档](https://developer.android.com/privacy-and-security/risks/cleartext-communications)称Android 9/API28起原生HTTP client默认禁止cleartext。HTTPS利于浏览器secure context，但IP证书和LAN用户信任也有交互成本，不应贸然宣称自动解决。需要PC Chrome/Android Chrome测HTTP、SSE、图片、音频、Wi-Fi切换和关闭listener。

区分动作：断远端访问（网络断/网页离开）、关闭LAN共享（host停止listener）、取消generation（task收到cancel）。Android共享中由FGS通知明确“局域网共享中”；只有共享服务受影响时显示关闭。文件、图片、剪贴板、OAuth browser用Android平台adapter，不复用桌面temp路径/子进程。

## 9. Android MVP保留与暂缓

| 类别 | 能力 |
|---|---|
| 原生MVP必须 | 本机角色列表/选择/导入；API key/baseURL/model配置；Persona/聊天创建；历史读取和长会话显示；单聊prompt/worldbook/context/provider stream；停止/错误/重试；重生成/续写基础语义；保存后重读；备份恢复；可选LAN Vue共享/配对/关闭 |
| 核心保留但原生暂不做编辑入口 | 群聊字段、memberSettings、reasoning/tool trace、TTS metadata、MVU/KG/regex、fork lineage、WorldBook高级设置、所有schema extra |
| 先由Vue管理 | 高级provider/cache/search、WorldBook条目精调、群聊高级管理、assistant tool权限、复杂导入映射、OAuth、WebGPU preset/appearance |
| 平台能力替代/禁用 | 文件及图片用SAF/Photo Picker；剪贴板走系统API；TTS用Android adapter或暂禁；OAuth回调用Android intent/deep link；桌面更新/本地模型子进程禁用 |
| 本轮不做 | Android本地模型/WebGPU推理、账号/多租户、公网host、host互同步/发现、桌面原生化、预先换数据库 |

群聊建议暂缓原生第一阶段不是其逻辑不能共享，而是要先把Vue的round queue/pause计划变server-owned task。Assistant tools、OAuth、TTS、WebGPU均不属于默认文字单聊闭包。API key+单协议即可先验证主链；后续逐项纳入。

即使native暂不展示字段，更新Character/Chat/Settings时必须patch指定字段并保留未识别字段；不能将简化后的客户端model覆盖全实体。备份至少确认settings、characters、chats、WorldBooks、avatars、images、memory sidecars/index相关引用，使用脱敏副本做恢复演练。

## 10. 最小纵向实验

本轮没有Android SDK/adb/Gradle，故未创建空壳。下一轮应只做能决策的小纵向POC，不建大量未验证脚手架。

### 前置条件与切片

- 一台arm64真机、adb、Android Studio/JDK/Gradle；锁定待支持minSdk/targetSdk/OS。当前工作环境只发现java/node/npm，无adb/gradle。
- Chaquopy候选runtime与精确Python/ABI依赖解析；先准备脱敏角色、chat、Persona、WorldBook、preset fixture，不复制data真实私人内容。
- 本机mock OpenAI-compatible provider SSE server，支持慢delta、错误、断流、取消；不打收费API。
- PC与手机同Wi-Fi，Chrome stable，第一版token配对方案；Vue production dist同源提供。

POC仅含Android原生薄UI、进程内Python Core bridge、单聊应用facade/必要storage-root与tokenizer适配、mock provider、可选LAN listener+dist+短期配对。既有Vue UI可以直接做PC客户端，但host须少量静态资源/可配置API origin适配；当前Vite proxy仅开发用，不能证明手机dist可加载。当前main.py宽启动会导入/初始化太多能力，不适合直接作为最小Android闭包。

### 模拟与真实Provider分开

**先做模拟：**手机UI读fixture角色/chat；Core本机组装context；调用手机mock server；流式delta展示并保存私有目录；重入同chat读取相同messageId/content。开LAN后PC浏览器加载手机提供的Vue并打开相同chat；PC产生mock回复后手机刷新可见同一revision。PC断网/关页时，task继续到完成；同request ID只创建一task；重新连接取状态/结果。关闭共享后listener端口不再服务，但native task独立。

**另列真实provider阶段：**模拟通过后可由作者在本机自行配置单个真实preset，做一次有限验证DNS/TLS/CA/provider兼容；本轮没有做、没有输出凭据，调查任务不调用收费模型服务。

### 记录与通过/失败

记录：APK分ABI包体、冷启动到列表、RSS/native heap、fixture消息数和字节量、chat load/save延时、context中实际message IDs/hash、首token/总时长、事件sequence是否丢失、message ID/body一致、Activity切换/锁屏/网页断开/kill process后task状态、两个UI revision冲突、端口占用/权限拒绝/Wi-Fi换IP、token撤销结果。

通过：所选精确依赖能装且能import；本机Core与桌面fixture生成语义一致；mock stream delta/error/cancel可控；app-private落盘并重读正确；符合目标的Activity/锁屏后台行为；PC Vue同源读取同一chat/message；断远端不取消host task；幂等、条件写、关闭listener、撤销配对均有效。

失败并切路线2：必需pydantic-core无可维护ABI；token计数替代会丢失不可接受的budget裁剪；需要把核心规则复制Kotlin才能完成；目标设备启动/RSS不接受；app-private write/lock不可靠；产品要求的持续后台任务不能在合法FGS策略下稳定实现。若只是可选能力（TTS、assistant）不兼容，则先禁用，不触发核心迁移。

进程被杀后不恢复上游同次generation可作为MVP限制，前提是记录interrupted、保留已保存内容并让用户明确重试。不要混淆客户端离线成功与provider续跑。

## 11. 本轮检查与失败记录

- git status --short --branch：master；已有未跟踪 .agents/、.codex/、PROJECT_STATE.md。检查时新报告不存在。本轮不改写这些内容。
- 搜索工作树未发现AGENTS.md；.agents含UI/roadmap skill但本调查不是其适用工作；.codex/agents是代理配置，不是AGENTS规则。
- 阅读PROJECT_STATE.md并以现行代码核对生成路由、schema、storage、Vue composable、API及启动边界。旧报告记录的前端npm build TS1117错误未重跑；不能在本轮称其为当前重验结果。
- 仓库Python launcher启动失败：指向缺失的Python312路径。使用workspace bundled Python 3.12.14读其自己的环境信息；SimpleTavern venv只从dist-info和扩展文件名静态读取。未运行后端import或启动服务。
- 工具检查未找到adb/gradle；未运行Android构建、服务器、provider、自动化测试。读取requirements与源码，未更新依赖。
- 官方web查询日期2026-09-29：Chaquopy 17 Android版本/ABI/minSdk、tokenizers官方wheel索引、Android FGS/Android15时限、LAN permission/Android17、cleartext以及MDN secure context/WebGPU。Wheel观察未运行resolver；pydantic-core是否可手工构建尚未知。
- 未读写真实数据、输出API key/OAuth token/聊天正文、调用收费模型；未提交Git。

## 12. 尚未解决的关键问题

以下应尽量用实验回答，不交给作者猜测技术可行性：

1. 当前Python版本/API/ABI下pydantic-core可否构建安装？所需recipe与长期维护面多大？
2. tokenizers>=0.15在arm64可否自编；若采用替代token计数，context裁剪与超长历史行为差异是否能接受？
3. 拆开单聊应用service后的真实必需import closure是什么？哪些lifespan工作可延迟/禁用？
4. 目标手机上的冷启动、RAM、app体积和长会话性能数据是多少？目标设备及接受阈值尚未提供。
5. 当前settings response是否redact API/OAuth secret，LAN配对用户能否管理provider secret，需要审接口。
6. 目标PC/Android浏览器版本访问手机LAN IP时HTTP POST SSE、图片、audio的具体安全/权限表现，须真机测。
7. 若日后迁Kotlin/JVM，现有Python fixture/行为验收如何建立，桌面Python何时退场？这要由路线试验的数据决定。

### 官方资料与查询版本

查询日为2026-09-29，平台文档会更新：

- Chaquopy current 17：[versions](https://chaquo.com/chaquopy/doc/current/versions.html)、[Android/Gradle配置与ABI](https://chaquo.com/chaquopy/doc/current/android.html)、[tokenizers wheel目录](https://chaquo.com/pypi-13.1/tokenizers/)。
- Android：[FGS overview](https://developer.android.com/develop/background-work/services/fgs)、[FGS后台启动限制](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)、[Android15变化](https://developer.android.com/about/versions/15/behavior-changes-15)、[LAN权限](https://developer.android.com/privacy-and-security/local-network-permission)、[Android17变化](https://developer.android.com/about/versions/17/behavior-changes-17)、[cleartext](https://developer.android.com/privacy-and-security/risks/cleartext-communications)。
- 浏览器：[Secure Contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)、[WebGPU](https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API)。

## 带回讨论摘要

SimpleTavern 已有可复用的Python单聊核心：它读取角色、Persona、Settings、聊天与WorldBook，组装/裁剪上下文，经多个provider adapter流式生成并写回本机JSON。但它不是现成Android包。依赖风险集中在Pydantic v2的Rust pydantic-core与tokenizers>=0.15；Chaquopy官方当前wheel索引只看到0.10.3及更低tokenizers。Android build/真机本轮未验证。

Vue当前独自持有群聊的随机参与、成员顺序、延迟、暂停和剩余队列；普通消息版本、regenerate操作也部分在页面内存。现有聊天端点没有历史分页、generation task ID/status/幂等或断线事件恢复；全Chat读取、整份JSON保存、无revision写保护意味着两个客户端有旧内容互相覆盖风险。

建议下一步先做小纵向POC：native UI进程内调用Python单聊service，mock provider逐delta返回并保存手机私有数据；开共享后PC浏览器加载手机host的Vue dist并访问同chat；远端断开时任务继续、同request ID幂等。通过依赖/性能/生命周期后继续方案1；关键Android native依赖或Python后台行为失败时评估Kotlin/JVM共享核心。Android-only重写仅适合短期对照。

MVP可以承诺host任务与浏览器连接分离、重连读取最终保存内容；主机被杀后显示interrupted，不承诺逐delta恢复或同一provider任务恢复。第一阶段以单聊、导入角色/历史、API key、停止/重试、备份恢复及可选配对LAN共享为主。群聊task、OAuth、TTS、assistant、WebGPU后置，所有隐藏字段仍须在native编辑时保留。

最大未知应由实验回答：精确Android wheel闭包、目标设备启动/RSS/后台行为、浏览器访问手机HTTP/SSE与配对边界。当前环境能证明源码调用路径、依赖声明和平台文档限制，不能证明Android上已跑通。
