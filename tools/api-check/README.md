# 黑盒接口检查

依据官方文档和 `docs/specs/BACKEND-API.md` 写的接口检查，不看后端实现。用来回答 T-814 的两项：

- `[自动]` 依据官方文档写的 T-832 独立黑盒检查通过，并且在 T-832 之前的版本上会失败。
- `[自动]` 核心接口的正向和负向黑盒检查通过（角色、会话、设置、备份导入、生成错误）。

## 运行

```bash
venv/Scripts/python tools/api-check/run.py                  # 全部
venv/Scripts/python tools/api-check/run.py --only t832,core # 只跑这两组
venv/Scripts/python tools/api-check/run.py --only t832.vertex.sa
venv/Scripts/python tools/api-check/run.py --list
```

每次运行都会：在 `temp/api-check/` 下建全新的空数据目录，启动后端（9701）、恢复演练用的第二个后端（9703）和模拟上游（9702），逐项打印 `PASS` / `FAIL` / `NOTE`，最后清理。有失败时退出码为 1。`--keep` 保留数据目录和后端日志。端口可用参数改，默认都在 9701 到 9719，不碰 9081、9091。只停自己启动的进程。

只用项目已有的依赖（httpx、PyJWT、cryptography），不用 pytest。测试用的 RSA 私钥、服务账号 JSON 和 API Key 每次运行时生成，不进仓库。

后端的 `HTTP(S)_PROXY` 指向模拟上游，`NO_PROXY` 放行本机：后端如果想访问外网，会在模拟上游留下 CONNECT 记录并被拒绝，`*.no_external_network` 检查这一点。后端的 HTTP 客户端如果不读代理环境变量，这道防线就无效。

## 分组

| 分组 | 内容 | 需要后端 |
|---|---|---|
| `selftest` | 证明编码和模拟服务本身是对的：用 AWS 文档里的样例帧核对 CRC 和帧结构；另写一个不用 zlib 的解码器解开自己编码的帧；每种故障注入发出的字节确实是坏的；模拟服务拒绝不符合文档的请求；token 端点拒绝伪造签名和错误声明 | 否 |
| `baseline` | 同一套流程走本分支已有的 `openai_compatible_chat` 和 `anthropic_messages`。这一组通过而 `t832` 失败，才能说明失败来自协议不支持，不是流程写错 | 是 |
| `core` | 核心接口的正向和负向 | 是 |
| `t832` | Bedrock Converse、Mistral Conversations、Vertex Anthropic、Bedrock 上的 Anthropic | 是 |

结果有三种：`PASS`、`FAIL`，以及 `NOTE`（规格未定义，只记录观察到的行为，不算通过也不算失败）。

## T-832 的对外约定

另一个子代理按这些约定实现，这里只按约定配置预设：

- Bedrock Converse：`protocol=bedrock_converse`，`apiKey` 作为 `Authorization: Bearer`，请求 `{baseUrl}/model/{modelId}/converse` 和 `/converse-stream`。
- Mistral：`protocol=mistral_conversations`，请求 `{baseUrl}/v1/conversations`。另有一项检查 `baseUrl` 带 `/v1`（目录模板的写法）时不会变成 `/v1/v1`。
- Vertex：`protocol=anthropic_messages`，`authStyle=vertex_service_account`，`apiKey` 是服务账号 JSON，`token_uri` 指向模拟服务，`baseUrl` 为 `http://127.0.0.1:<port>/v1/projects/p/locations/us-east5`，请求 `{baseUrl}/publishers/anthropic/models/{model}:streamRawPredict` 和 `:rawPredict`。
- Bedrock 上的 Anthropic：`protocol=anthropic_messages`，`authStyle=bearer`，`providerParams._host=bedrock-runtime.invalid`（`.invalid` 保证不会真的解析到 AWS），请求 `/model/{model}/invoke` 和 `/invoke-with-response-stream`。

每一项都先确认请求真的到了这一家的模拟上游、没有违反文档，再看结果。否则协议不支持时后端也会回一个结构化错误，负向检查会误判为通过。

## 模拟上游怎么校验

全部依据下面的文档，请求不符合就记一条违规，并按该服务的错误格式返回 400/401/403：

- 路径和方法、鉴权头（Bedrock 和 Mistral 是 Bearer API Key，Vertex 只认 token 端点发出的 access token）、Content-Type。
- Converse：顶层字段只能是文档里的；`messages` 第一条是 user，role 只能是 user/assistant，内容块是只有一个成员的联合类型；`system` 文本至少 1 个字符；`inferenceConfig` 的字段和范围；`toolSpec.name` 的格式和 `inputSchema.json`；`toolResult` 前面必须有对应的 `toolUse`。
- Anthropic（Vertex 和 Bedrock）：`anthropic_version` 分别是 `vertex-2023-10-16` 和 `bedrock-2023-05-31`；请求体不能有 `model`；Vertex 的 `stream` 和接口一致，Bedrock 的请求体字段里没有 `stream`；`max_tokens` 必填；`thinking.budget_tokens` 至少 1024 且小于 `max_tokens`；回传的 thinking 块要带签名。
- Mistral：顶层字段只能是文档里的，`inputs` 必填，`model` 和 `agent_id` 至少一个，inputs 的 role 只能是 user/assistant（系统提示要放 `instructions`），`function.result` 前面要有对应的 `function.call`，`completion_args` 的字段。
- Google token 端点：POST、`application/x-www-form-urlencoded`、`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`；JWT 头 `alg=RS256`、`typ=JWT`、`kid` 若有须等于 `private_key_id`；用服务账号公钥验签；`iss` 是服务账号邮箱，`scope` 含 `cloud-platform`，`aud` 是 `token_uri` 或文档里的 `https://oauth2.googleapis.com/token`（两种都接受），`iat` 是当前时间，`exp - iat` 不超过 1 小时。
- 任何请求头里都不能出现私钥或服务账号 JSON。

响应同样按文档构造：eventstream 是真实的二进制帧和 CRC32，前几帧拆成 1 到 29 字节的 TCP 片段发送（跨越前导和多字节字符），后面的帧两两粘在一起发；第一帧带全部十种头部类型；事件里带真实 AWS 会有的 `p` 填充字段；用量放在 `messageStop` 之后的 `metadata` 里。SSE 也拆碎发送。

## 覆盖范围

T-832，每家：

- 正向：流式和非流式文字完整、顺序正确、真流式（多个 delta）、落盘到会话；用量归一化（消息、响应、账本）；缓存读写用量；思考内容和正文分开；系统提示、`max_tokens`、`temperature` 映射到协议字段；第二轮带历史，回传思考块时文字和签名原样；不认识的事件不影响文字；开场白开头的会话；会话中间有系统消息；助手工具往返（工具定义、调用、结果回传、最后回答落盘），思考开启时带签名的思考块原样回传；写作辅助和群聊走同一协议。
- 负向：流式上游 401/403/429/500/503，非流式 401/403/429/500，映射为有 `code`、`message`、`requestId` 的错误，401/403 是 `provider_auth_failed` 且不可重试，429/5xx 可重试；流中断、无终止事件、畸形 JSON、流内异常事件不算成功、不悬挂，用户消息保留，账本 `completedCount` 为 0；eventstream 另测前导中断、前导 CRC 错、消息 CRC 错、内部异常、未建模错误；非流式畸形 JSON、截断、200 但没有输出。
- 密钥：成功和失败后，生成响应、会话、会话导出、账本事件、HTTP 日志列表和详情、后端日志里没有 API Key、私钥、access token 和 JWT；上游错误信息回显凭据时同样检查。
- Vertex：JWT 换 token 并用于调用；服务账号不是 JSON、不是对象、为空、缺 `client_email`/`private_key`/`token_uri`、私钥坏、`type` 不对时明确报错且不发请求；token 端点 400、500、非 JSON、缺 `access_token`、连接中断时明确报错且不调 Vertex。
- Bedrock：推理配置文件 ARN（含斜杠和冒号）整体编码成一个路径段。

核心：请求标识、健康检查；角色、会话、消息、世界书、设置的增删改查和读回；不存在的 id、非法字段、错误类型、非 JSON 请求体、路径穿越；分叉；全文检索；世界书注入（全局、绑定会话、停用条目、会话内移除全局书）；三种备份范围的 ZIP 内容；`with_chats` 备份导入另一个空数据目录后逐项读回；后端重启后数据还在；生成的错误路径（会话不存在、预设不存在、非法请求体、上游 401/429/500、连不上、畸形 JSON、200 但没有输出）和成功路径的事件顺序、落盘、账本、requestId；上游回显 Key 时的打码；用量接口的参数校验。

## 对照怎么做的

- T-832：在没有 T-832 实现的分支上跑，`t832` 组应失败，并逐项看失败原因（后端返回 `provider_capability_unsupported`，或 Vertex 预设被当成普通 Anthropic 打到 `{baseUrl}/messages`）。同时 `baseline` 组必须通过。
- 核心：没有“修改前的版本”可比，用一次性的故意出错的代理做对照：一种模式让写操作只回显不落盘，另一种把 4xx/5xx 改成 200。每项核心检查至少在一种模式下失败，除了与这两种破坏无关的几项（请求标识、健康检查、外网访问）。这个代理不在本目录里。

## 测不到的东西

- 真实的 AWS、Mistral、Google 服务。模拟服务只照文档，文档没写或写错的地方测不到；真实服务的错误格式、限流细节、模型差异都可能不同。T-814 里 Vertex 的真实项目验收仍由作者做。
- 上游连接一直不发数据（停滞）：要等后端自己的超时，规格没写时长，没有测。
- 图片、文档等多模态内容块，引用（citations），护栏（guardrail），`stopReason` 为 `max_tokens`、`content_filtered`、`refusal` 时的表现。
- Converse 消息必须 user/assistant 交替：文档没写死，没有校验。
- Bedrock Converse 如何映射思考档位：规格没写，检查只在请求里带了 `additionalModelRequestFields.thinking` 时才验证思考块回传。
- token 是否缓存复用：只记录次数（`NOTE`）。
- 前端如何展示这些错误：这里只看接口。
- T-832 的正向检查还没有在任何真实实现上跑通过。实现合并后第一次运行时，失败要先分清是检查写错还是实现的问题。

## 依据的文档

- AWS Bedrock Converse：https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- AWS Bedrock ConverseStream：https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html
- 内容块和增量：`API_runtime_ContentBlock`、`API_runtime_ContentBlockDelta`、`API_runtime_ReasoningContentBlockDelta`、`API_runtime_ReasoningTextBlock`、`API_runtime_ToolSpecification`、`API_runtime_ToolUseBlockStart`、`API_runtime_ToolUseBlockDelta`、`API_runtime_ToolResultBlock`（同一目录下）
- InvokeModelWithResponseStream：https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModelWithResponseStream.html
- Bedrock 上的 Anthropic 请求体：https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html
- Bedrock API Key：https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
- eventstream 编码：https://smithy.io/2.0/aws/amazon-eventstream.html ，样例帧和 CRC32 说明：https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html
- Mistral Conversations：https://docs.mistral.ai/api/endpoint/beta/conversations ，事件和字段以官方 Python SDK 的模型文档为准：https://github.com/mistralai/client-python/tree/main/docs/models （`conversationrequest`、`ssetypes`、`messageoutputevent`、`functioncallevent`、`responsedoneevent`、`responseerrorevent`、`conversationusageinfo`、`messageoutputentry`、`functioncallentry`、`functionresultentry`、`completionargs`、`thinkchunk`）
- Vertex 上的 Claude：https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/use-claude
- Google 服务账号 JWT：https://developers.google.com/identity/protocols/oauth2/service-account
- Anthropic 流式事件：https://platform.claude.com/docs/en/build-with-claude/streaming
