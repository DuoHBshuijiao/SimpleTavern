# SimpleTavern 后端 API 规范

本文只描述对外 HTTP/SSE 接口的功能与数据约定，供仓库外黑盒测试编写用例。不描述内部函数、实现细节或自动化门禁。

覆盖范围：OpenAPI 共 **107** 条路径、**132** 个 HTTP 操作（同一路径上的 GET/PUT/DELETE 等分别计数）。另有 FastAPI 自带 `/docs`、`/redoc`、`/openapi.json`，非正式产品接口。

应用形态：本机单用户。前端默认 `http://127.0.0.1:9081`，后端默认 `http://127.0.0.1:9091`。浏览器请求走 `/api/*`，由前端开发服务器代理到后端。无登录鉴权；OAuth 仅用于向上游 LLM 厂商取 token。

并行沙箱：`python sandbox.py` 使用 `http://127.0.0.1:9181` / `http://127.0.0.1:9191` 与目录 `data-sandbox/`（环境变量 `SIMPLETAVERN_DATA_DIR`）。不改写生产 `data/`，也不占用生产端口。用法见 [`docs/SANDBOX.md`](../SANDBOX.md)。

持久化：JSON 文件位于仓库 `data/`（设置、角色、会话、世界书、头像、字体、背景、TTS 缓存、OAuth token 等）。沙箱写入 `data-sandbox/`。

## 通用约定

### 请求标识

- 客户端可发送请求头 `X-Request-Id`：须匹配 `^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`，否则服务端忽略并自行生成。
- 服务端生成形如 `req_` + 32 位 hex。
- 成功与失败响应均回传 `X-Request-Id`。

### 错误信封（REST JSON）

失败时 JSON 主体字段（camelCase）：

- `code`（string）：稳定错误码，如 `request_validation_failed`、`not_found`、`upstream_timeout`、`provider_auth_failed`、`generation_failed`、`MISSING_OAUTH_LOGIN`。
- `message`（string）：面向用户的说明；密钥等敏感片段会被打码。
- `detail`（string | null）：补充细节，同样打码，过长截断。
- `source`（string）：出错子系统，如 `generate.stream`、`llm.registry`。
- `retryable`（boolean）
- `requestId`（string）
- `provider` / `protocol` / `upstreamStatus`（可选）
- `suggestedAction`（string，可选）：建议操作文案
- `action`（object，可选）：前端可执行动作，例如 `{ type: "open_settings", tab, presetId, field, label }`

校验失败 HTTP 422；业务缺失常见 404；上游超时 504；上游不可达/协议错误 502。部分旧路径的 `HTTPException.detail` 可能是字符串或 `{code,message,chatId}`，客户端应兼容。

### SSE 公共格式

流式接口 `Content-Type: text/event-stream`。每帧：

```
event: <name>
data: {JSON}

```

生成类接口（`/api/generate/*`、写作辅助）事件：

- `meta`：开流。`requestId`；可选 `provider`、`protocol`、`resolvedModel`、`warnings[]`、`protocolResolution`、`cache`。
- `reasoning`：`{ text }` 思考增量。
- `delta`：`{ text }` 正文增量。
- `done`：终态成功。至少 `ok: true`、`chatId`；常含 `assistantMessageId`、`reasoningContent`、`reasoningDurationSec`、`usage`。群聊另含 `characterId`。
- `error`：终态失败。错误信封字段 + `terminal: true`。出现 error 时不再发 `done`。

`usage` 对象归一化后常见键：`input_tokens` / `output_tokens` / `total_tokens` / `reasoning_tokens`，以及缓存读/写相关字段、Fast 是否被请求的标记（供「Fast 未生效」徽标）。

当全局设置 `streamEnabled=false` 时，生成类接口改为一次性 JSON（非 SSE），成功体含 `ok`、`chatId`、助手正文/思考/usage；失败仍为错误信封。

助手 `/api/assistant/stream` 额外事件：`tool_record`、`tool_trace`、`card`、`chat_memory_updated`、`worldbook_updated`、`chat_overrides_updated`。

MVU `/api/mvu/{chat_id}/stream`：先补发最多 50 条 `log_history`，随后实时 `log_entry` 等 `kind`，空闲 `heartbeat`。

### 命名提示

- `POST /api/llm/test-models`、`POST /api/tts/test-voices` 是**产品内的连通性探测**（拉上游模型/音色列表），不是仓库内自动化测试。

## 接口一览

### health

#### `GET /api/health`

进程存活探测，成功体 `{ ok: true }`。

**响应**

- `200` `application/json` Successful Response → `object`

#### `GET /api/web-search/status`

Web Search Status

**响应**

- `200` `application/json` Successful Response → `any`

### settings

#### `GET /api/settings`

读取全局设置（含 LLM、预设、主题、TTS、世界书默认扫描深度、正文正则库、MVU 模型、网络搜索密钥配置等）。

**响应**

- `200` `application/json` Successful Response → `Settings`
  引用模型 `Settings`（字段见文末「数据模型」）。

#### `PUT /api/settings`

整份覆盖保存全局设置。单用户本地写盘。

**请求体**

Content-Type: `application/json`

引用模型 `Settings`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Settings`
  引用模型 `Settings`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

### characters

#### `GET /api/characters`

获取所有角色列表

**响应**

- `200` `application/json` Successful Response → `array<CharacterCard>`
  数组，元素类型 `CharacterCard`。
  引用模型 `CharacterCard`（字段见文末「数据模型」）。

#### `POST /api/characters`

创建新角色 前端可直接传递完整的角色卡片。如果未设置createdAt，则自动设置当前时间。 自动更新updatedAt为当前时间。

**请求体**

Content-Type: `application/json`

引用模型 `CharacterCard`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `CharacterCard`
  引用模型 `CharacterCard`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/characters/{character_id}`

获取指定角色

**参数**

- `character_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `CharacterCard`
  引用模型 `CharacterCard`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/characters/{character_id}`

更新角色 保留原有的createdAt时间戳（避免编辑时覆盖）。 如果URL中的character_id与card.id不一致，以URL中的ID为准。 自动更新updatedAt为当前时间。

**参数**

- `character_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `CharacterCard`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `CharacterCard`
  引用模型 `CharacterCard`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/characters/{character_id}`

删除角色 同时会删除该角色关联的所有聊天会话。

**参数**

- `character_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### chats

#### `GET /api/chats`

`characterId` 必填。`summary=true` 时侧栏摘要，不含 `messages`。

**参数**

- `characterId`（query，必填，string）
- `summary`（query，可选，boolean，默认 false）：为 true 时仅返回侧栏摘要（无 messages）

**响应**

- `200` `application/json` Successful Response → `array<Chat>`
  数组，元素类型 `Chat`。
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats`

创建单聊或群聊。可从角色继承 MVU 指令模式。

**请求体**

Content-Type: `application/json`

引用模型 `CreateChatRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/chats/groups`

群聊列表。`summary=true` 时不含消息。

**参数**

- `summary`（query，可选，boolean，默认 false）：为 true 时仅返回侧栏摘要（无 messages）

**响应**

- `200` `application/json` Successful Response → `array<Chat>`
  数组，元素类型 `Chat`。
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{source_chat_id}/promote-to-group`

单聊复制为群聊。

**参数**

- `source_chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `PromoteToGroupRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{source_chat_id}/branch`

创建分支会话。

**参数**

- `source_chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{source_chat_id}/fork`

从指定消息处分叉出会话，保留到该消息为止的历史。

**参数**

- `source_chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `ForkChatRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/chats/{chat_id}/fork-lineage`

分叉溯源：来源、兄弟分叉、从本会话拉出的子分叉（fork_index，不加载源会话）。

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `ForkLineageResponse`
  引用模型 `ForkLineageResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/chats/{chat_id}`

获取指定聊天会话

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/chats/{chat_id}`

更新聊天会话 支持更新标题、群聊延迟、成员列表（仅重排）、成员设置、用户Persona和覆盖设置。 对于群聊的memberIds更新，仅允许重排（成员集合必须一致）。

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `UpdateChatRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/chats/{chat_id}`

删除聊天会话

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/chats/{chat_id}/search`

在当前会话正文中全文检索。

**参数**

- `chat_id`（path，必填，string）
- `q`（query，必填，string）

**响应**

- `200` `application/json` Successful Response → `ChatSearchResponse`
  引用模型 `ChatSearchResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{chat_id}/messages`

向聊天会话追加消息

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `AppendMessageRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/chats/{chat_id}/messages/{message_id}`

更新聊天会话中的消息 支持更新消息的角色、内容、角色ID和发送者快照信息。 发送者快照用于在切换Persona时保持历史消息的显示一致性。

**参数**

- `chat_id`（path，必填，string）
- `message_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `UpdateMessageRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/chats/{chat_id}/messages/{message_id}`

删除聊天会话中的消息

**参数**

- `chat_id`（path，必填，string）
- `message_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/chats/{chat_id}/messages/{message_id}/save-and-truncate`

将该消息标为记忆锚点并截断其后上下文。

**参数**

- `chat_id`（path，必填，string）
- `message_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `UpdateMessageRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{chat_id}/images`

上传会话图片，返回附件元数据。 主聊天当前仅支持图片，且单文件上限与助手图片附件保持一致为 100MB。

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `UploadChatImagesRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `UploadChatImagesResponse`
  引用模型 `UploadChatImagesResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/chats/{chat_id}/images/{image_id}`

读取会话图片文件。

**参数**

- `chat_id`（path，必填，string）
- `image_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/chats/{chat_id}/members/{member_id}`

向群聊添加成员 只能向群聊添加成员。会检查角色是否存在，如果成员已存在则不做任何操作。

**参数**

- `chat_id`（path，必填，string）
- `member_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/chats/{chat_id}/members/{member_id}`

从群聊移除成员 只能从群聊移除成员。如果成员不存在则不做任何操作。

**参数**

- `chat_id`（path，必填，string）
- `member_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `Chat`
  引用模型 `Chat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

### generate

#### `POST /api/generate/stream`

单聊生成。默认把用户消息写入会话。`mergeAssistantIntoMessageId` 时把输出并入已有助手消息的新版本。`webSearchEnabled` 需已配置 Tavily/博查，否则 fast-fail。`omitMessageIds` 仅本次拼装忽略。

**请求体**

Content-Type: `application/json`

引用模型 `GenerateStreamRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/generate/draft-help`

写作辅助：`write` 续写用户发言，`enhance` 润色草稿。临时 `conversation` 不落盘。

**请求体**

Content-Type: `application/json`

引用模型 `DraftHelpRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/generate/group`

群聊指定角色回合。成员设置中的模型/温度/思考深度/Fast 优先于会话再全局。

**请求体**

Content-Type: `application/json`

引用模型 `GroupGenerateRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/generate/interject`

群聊插话：指定角色额外回复一轮，不推进正常轮转。

**请求体**

Content-Type: `application/json`

引用模型 `SingleInterjectRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

### llm

#### `GET /api/llm/models`

从全局设置读取配置并拉取模型列表；失败不伪装本地候选。

**响应**

- `200` `application/json` Successful Response → `array<string>`
  数组，元素类型 `string`。

#### `POST /api/llm/test-models`

使用请求内凭证测试模型列表，不依赖全局设置。

**请求体**

Content-Type: `application/json`

引用模型 `TestModelsRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `array<string>`
  数组，元素类型 `string`。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/llm/catalog`

内建供应商/模型目录（协议、鉴权样式、缓存策略、建议模型）。

**响应**

- `200` `application/json` Successful Response → `object`

#### `POST /api/llm/model-capabilities`

T-824：模型能力（可用思考深度 / Fast 模式 / 成本），供聊天面板即时渲染。

**请求体**

Content-Type: `application/json`

引用模型 `ModelCapabilitiesRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/resolve-preview`

不消耗 api_key。预览本次将使用的协议、URL、思考档位、Fast、缓存计划与翻译说明。

**请求体**

Content-Type: `application/json`

引用模型 `ResolvePreviewRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### llm-oauth

#### `GET /api/llm/oauth/status`

Oauth Status

**参数**

- `presetId`（query，可选，string | null）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/oauth/start`

启动 Copilot 设备码或 Codex 设备码/PKCE。

**请求体**

Content-Type: `application/json`

引用模型 `OAuthStartRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/oauth/poll`

Oauth Poll

**请求体**

Content-Type: `application/json`

引用模型 `OAuthSessionRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/oauth/complete-pkce`

Oauth Complete Pkce

**请求体**

Content-Type: `application/json`

引用模型 `OAuthCompletePkceRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/oauth/cancel`

Oauth Cancel

**请求体**

Content-Type: `application/json`

引用模型 `OAuthSessionRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/llm/oauth/logout`

Oauth Logout

**请求体**

Content-Type: `application/json`

引用模型 `OAuthLogoutRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### assistant

#### `GET /api/assistant/workspace/character-card`

获取工作空间角色卡草稿。 缺失返回 data_not_found；损坏返回 data_corrupted；成功直接返回 CharacterCard。

**响应**

- `200` `application/json` Successful Response → `CharacterCard`
  引用模型 `CharacterCard`（字段见文末「数据模型」）。

#### `PUT /api/assistant/workspace/character-card`

保存工作区角色卡草稿 写入 data/ai_workspace/character_card.json，供助手工具 workspace_write_file 与前端共用同一暂存位置。

**请求体**

Content-Type: `application/json`

引用模型 `CharacterCard`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `CharacterCard`
  引用模型 `CharacterCard`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/attachments/ingest`

将助手附件写入 ai_workspace/ingest，并返回稳定附件元数据。

**请求体**

Content-Type: `application/json`

引用模型 `AssistantAttachmentIngestRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `AssistantAttachmentIngestResponse`
  引用模型 `AssistantAttachmentIngestResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/assistant/attachments/{attachment_id}`

读取助手消息附件。工作区会在会话清理后返回 404，供前端降级展示。

**参数**

- `attachment_id`（path，必填，string）
- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）
- `storageScope`（query，可选，string | null）
- `storageKey`（query，可选，string | null）
- `filename`（query，可选，string | null）
- `mimeType`（query，可选，string | null）
- `kind`（query，可选，string | null）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/workspace/session/cleanup`

按 sessionId 删除工作区临时附件目录。

**请求体**

Content-Type: `application/json`

引用模型 `WorkspaceSessionCleanupRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/assistant/settings`

获取AI助手设置（响应中不包含 prompt）。

**响应**

- `200` `application/json` Successful Response → `AssistantSettings`
  引用模型 `AssistantSettings`（字段见文末「数据模型」）。

#### `PUT /api/assistant/settings`

更新AI助手设置：请求体中未出现的字段保留原值。系统提示词由 AGENT.md 提供，不依赖本接口。

**请求体**

Content-Type: `application/json`

引用模型 `AssistantSettingsUpdate`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `AssistantSettings`
  引用模型 `AssistantSettings`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/assistant/chat`

获取AI助手聊天记录

**参数**

- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）

**响应**

- `200` `application/json` Successful Response → `AssistantChat`
  引用模型 `AssistantChat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/chat/messages`

向助手聊天追加一条消息（用于流式中断时保存截断内容）。

**参数**

- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）

**请求体**

Content-Type: `application/json`

引用模型 `AppendAssistantMessageRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `AssistantChat`
  引用模型 `AssistantChat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/reset`

重置AI助手聊天 清空聊天记录；聊天作用域只清理自身 ingest 附件目录，不影响整个 ai_workspace。

**参数**

- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/workspace/chat/delete`

删除工作空间聊天记录

**响应**

- `200` `application/json` Successful Response → `object`

#### `PUT /api/assistant/chat/messages/{message_id}`

更新AI助手消息

**参数**

- `message_id`（path，必填，string）
- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）

**请求体**

Content-Type: `application/json`

引用模型 `UpdateMessageRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `AssistantChat`
  引用模型 `AssistantChat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/assistant/chat/messages/{message_id}`

删除AI助手消息

**参数**

- `message_id`（path，必填，string）
- `chatId`（query，可选，string | null）
- `scope`（query，可选，string | null）

**响应**

- `200` `application/json` Successful Response → `AssistantChat`
  引用模型 `AssistantChat`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/assistant/stream`

流式 AI 助手对话。 支持工具调用、多轮对话、推理内容等；作用域可为 workspace 或 chat。 长期记忆写入与破坏性工具是否可用仅由请求体中的 allowWriteMemory、 allowDestructiveTools 决定（工作区作用域下不会开启记忆写入）。

**请求体**

Content-Type: `application/json`

引用模型 `AssistantStreamRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

### mvu

#### `GET /api/mvu/{chat_id}/stream`

Stream Mvu Work Log

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/mvu/{chat_id}/health`

会话级 MVU worker health（含 SSE/queue dropped）。

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/content-regex/health`

全局正文正则 scanner health。

**响应**

- `200` `application/json` Successful Response → `any`

#### `GET /api/mvu/{chat_id}/state`

Get Mvu State

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/mvu/{chat_id}/state`

Update Mvu State

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `StateVariables`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/mvu/{chat_id}/knowledge-graph`

Get Knowledge Graph

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/mvu/{chat_id}/knowledge-graph`

Clear Knowledge Graph

**参数**

- `chat_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/mvu/{chat_id}/knowledge-graph/entities`

Upsert Knowledge Graph Entity

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `KgEntityUpsertBody`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/mvu/{chat_id}/knowledge-graph/entities/{entity_id}`

Delete Knowledge Graph Entity

**参数**

- `chat_id`（path，必填，string）
- `entity_id`（path，必填，string）
- `expectedVersion`（query，可选，integer | null）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/mvu/{chat_id}/knowledge-graph/relations`

Upsert Knowledge Graph Relation

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `KgRelationUpsertBody`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/mvu/{chat_id}/knowledge-graph/relations`

Delete Knowledge Graph Relation

**参数**

- `chat_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `KgRelationDeleteBody`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

### worldbooks

#### `GET /api/worldbooks`

Get Worldbooks

**响应**

- `200` `application/json` Successful Response → `array<WorldBook>`
  数组，元素类型 `WorldBook`。
  引用模型 `WorldBook`（字段见文末「数据模型」）。

#### `POST /api/worldbooks`

Create Worldbook

**请求体**

Content-Type: `application/json`

引用模型 `WorldBook`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `WorldBook`
  引用模型 `WorldBook`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/worldbooks/{worldbook_id}`

Get Worldbook

**参数**

- `worldbook_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `WorldBook`
  引用模型 `WorldBook`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/worldbooks/{worldbook_id}`

Update Worldbook

**参数**

- `worldbook_id`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `WorldBook`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `WorldBook`
  引用模型 `WorldBook`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/worldbooks/{worldbook_id}`

Remove Worldbook

**参数**

- `worldbook_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### import_export

#### `GET /api/chats/{chat_id}/export`

导出聊天会话 支持 txt、json、jsonl 三种格式。 - txt: 系统提示词 + 精简消息（Version 2：头部 Participants 为角色名，消息仅 role/name/content，与 JSONL 名映射一致） - json: 完整聊天对象（indent=2） - jsonl: 精简 NDJSON，每条消息一行，仅含 role/name/content，体积最小

**参数**

- `chat_id`（path，必填，string）
- `format`（query，可选，string，默认 "txt"）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/characters/{character_id}/export`

Export Character

**参数**

- `character_id`（path，必填，string）
- `include_world_books`（query，可选，boolean，默认 false）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/settings/backup`

备份设置 将设置、角色、聊天等数据打包为zip文件。支持三种范围： - basic: 仅设置和Persona头像 - with_characters: 包含角色和角色头像 - with_chats: 包含所有聊天记录

**参数**

- `scope`（query，可选，string，默认 "basic"）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/janitor/pending`

Import Janitor Pending

**请求体**

Content-Type: `application/json`

类型 `object`。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/import/janitor/pending/{pending_id}`

Get Janitor Pending Preview

**参数**

- `pending_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/janitor/confirm`

Confirm Janitor Import

**请求体**

Content-Type: `application/json`

引用模型 `JanitorConfirmRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/sillytavern/preview`

SillyTavern 包预览，不落盘。

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_preview_sillytavern_import_api_import_sillytavern_preview_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/sillytavern/confirm`

Confirm Sillytavern Import

**请求体**

Content-Type: `application/json`

引用模型 `SillyTavernConfirmRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/sillytavern/materialize`

由预览 pending 生成角色卡与世界书 JSON（不写库），用于头像裁剪合并编辑等。

**请求体**

Content-Type: `application/json`

引用模型 `SillyTavernMaterializeRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import/janitor/character-json`

Import Janitor Character Json

**响应**

- `200` `application/json` Successful Response → `object`

#### `POST /api/import/janitor/character-html`

Import Janitor Character Html

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_import_janitor_character_html_api_import_janitor_character_html_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/import`

通用导入（角色/世界书/设置/聊天等），返回 imported 列表与 warnings。

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_import_data_api_import_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### tts

#### `GET /api/tts/cache/stats`

返回缓存统计（ttsEnabled 关闭时仍允许查询，返回 usedBytes=0）。

**响应**

- `200` `application/json` Successful Response → `any`

#### `DELETE /api/tts/cache/clear`

手动清空 TTS 缓存。

**响应**

- `200` `application/json` Successful Response → `any`

#### `POST /api/tts/synthesize`

合成语音，可绑定消息；返回音频资源 id。

**请求体**

Content-Type: `application/json`

引用模型 `SynthesizeReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/bind-message`

将已合成的 TTS 资产绑定到服务端消息（补写 ttsAudioAssetId / ttsAudioSourceText）。

**请求体**

Content-Type: `application/json`

引用模型 `BindMessageReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/tts/audio/{asset_id}`

通过 UUID 获取已缓存的音频文件。

**参数**

- `asset_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/voices`

查询可用音色列表。

**请求体**

Content-Type: `application/json`

引用模型 `VoicesReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/test-voices`

使用临时 API 配置查询可用音色，供预设编辑器使用。

**请求体**

Content-Type: `application/json`

引用模型 `TestVoicesReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/glm-local/health`

检查 GLM-TTS 本地服务是否就绪。

**请求体**

Content-Type: `application/json`

引用模型 `GlmLocalActionReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/glm-local/clear-vram`

调用本地 GLM-TTS 的 clear_vram 接口释放显存。

**请求体**

Content-Type: `application/json`

引用模型 `GlmLocalActionReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/glm-local/start`

启动托管的 GLM-TTS 本地子进程。

**请求体**

Content-Type: `application/json`

引用模型 `GlmLocalStartReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/qwen3-local/health`

检查 Qwen3-TTS 本地服务是否就绪。

**请求体**

Content-Type: `application/json`

引用模型 `Qwen3LocalActionReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/qwen3-local/start`

启动托管的 Qwen3-TTS 本地子进程。

**请求体**

Content-Type: `application/json`

引用模型 `Qwen3LocalStartReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/omnivoice-local/health`

检查 OmniVoice 本地服务是否就绪。

**请求体**

Content-Type: `application/json`

引用模型 `OmniVoiceLocalActionReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/omnivoice-local/start`

启动托管的 OmniVoice 本地子进程。

**请求体**

Content-Type: `application/json`

引用模型 `OmniVoiceLocalStartReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/preprocess`

文本后处理：为 TTS 整理文本，可选注入兼容标签。

**请求体**

Content-Type: `application/json`

引用模型 `PreprocessReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/design`

使用临时 API 配置执行音色设计，并返回试听地址。

**请求体**

Content-Type: `application/json`

引用模型 `DesignVoiceReq`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/tts/clone`

使用临时 API 配置执行音色快速复刻，并返回试听地址。

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_clone_voice_api_tts_clone_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

### avatars

#### `POST /api/avatars`

上传头像 接受base64编码的图片数据，支持data URL格式。 自动识别图片格式（png/jpg/gif/webp），如果未指定文件名则生成UUID文件名。

**请求体**

Content-Type: `application/json`

引用模型 `UploadAvatarRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `UploadAvatarResponse`
  引用模型 `UploadAvatarResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/avatars/{filename}`

获取头像文件 根据文件扩展名设置正确的媒体类型。

**参数**

- `filename`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/avatars/{filename}`

删除头像文件

**参数**

- `filename`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### fonts

#### `GET /api/fonts`

列出 data/fonts 下所有字体文件名（仅允许的扩展名）。

**响应**

- `200` `application/json` Successful Response → `array<string>`
  数组，元素类型 `string`。

#### `POST /api/fonts`

上传字体文件到 data/fonts。导入后实时替换为当前选中字体，不随备份导出。

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_upload_font_api_fonts_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/fonts/{filename}`

返回字体文件，用于前端 @font-face url()。

**参数**

- `filename`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

### page-backgrounds

#### `GET /api/page-backgrounds/{filename}`

返回页面背景图文件。

**参数**

- `filename`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `any`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/page-backgrounds/{filename}`

删除页面背景图文件。

**参数**

- `filename`（path，必填，string）

**响应**

- `204` Successful Response
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/page-backgrounds`

上传页面背景图到 data/page_backgrounds，并返回生成后的安全文件名。

**请求体**

Content-Type: `multipart/form-data`

引用模型 `Body_upload_page_background_api_page_backgrounds_post`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `map<string, string>`
- `422` `application/json` Validation Error → `HTTPValidationError`

### shader-presets

#### `GET /api/shader-presets/{filename}`

返回 WebGPU 着色器预设源码（WGSL）。

**参数**

- `filename`（path，必填，string）

**响应**

- `200` `text/plain` Successful Response → `string`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `PUT /api/shader-presets/{filename}`

覆盖保存指定 WGSL 预设源码。

**参数**

- `filename`（path，必填，string）

**请求体**

Content-Type: `application/json`

引用模型 `ShaderPresetUpdateRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `ShaderPresetMutationResponse`
  引用模型 `ShaderPresetMutationResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/shader-presets/{filename}`

删除指定 WGSL 预设文件。文件已不存在时仍返回 204（幂等）。

**参数**

- `filename`（path，必填，string）

**响应**

- `204` Successful Response
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/shader-presets`

创建一个默认 WGSL 预设文件，并返回生成后的文件名。

**响应**

- `200` `application/json` Successful Response → `ShaderPresetMutationResponse`
  引用模型 `ShaderPresetMutationResponse`（字段见文末「数据模型」）。

### tokenizer

#### `GET /api/tokenizer/health`

Tokenizer 可用性（unavailable 不等于 0 token）。

**响应**

- `200` `application/json` Successful Response → `object`

#### `POST /api/tokenizer/count`

计算给定文本的 token 数（用于长期记忆等）。 请求体: { "text": "..." } 响应: { "tokens": number | null }，null 表示 tokenizer 不可用。

**请求体**

Content-Type: `application/json`

引用模型 `CountTextRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `GET /api/tokenizer/chat-count`

计算指定会话 chat.json 中对话内容的 token 数，以及自上次保存记忆以来的消息条数与 token 数。 响应: { "tokens": number | null, "messagesSinceLastMemoryUpdate": number | null, "tokensSinceLastMemoryUpdate": number | null }

**参数**

- `chatId`（query，必填，string）：会话 ID

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### http-log

#### `GET /api/http-log/health`

出站 HTTP 日志写盘健康（写失败计数）。

**响应**

- `200` `application/json` Successful Response → `object`

#### `GET /api/http-log`

返回最近 N 分钟的记录元数据；从新到旧排序（最新在上）。

**参数**

- `minutes`（query，可选，integer，默认 30）
- `limit`（query，可选，integer，默认 500）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/http-log`

清空全部日志。

**响应**

- `200` `application/json` Successful Response → `object`

#### `GET /api/http-log/{record_id}`

返回单条完整记录（含 request/response 原始内容）。

**参数**

- `record_id`（path，必填，string）

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### data-integrity

#### `GET /api/data-integrity/issues`

Get Data Integrity Issues

**响应**

- `200` `application/json` Successful Response → `object`

#### `POST /api/data-integrity/repair`

按扫描结果执行可自动修复项（如删除孤儿引用）。

**请求体**

Content-Type: `application/json`

类型 `DataIntegrityRepairRequest | null`。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

### clipboard

#### `POST /api/clipboard/resolve-rich-paste`

解析粘贴的 HTML/file URL 为本地可用图片。

**请求体**

Content-Type: `application/json`

引用模型 `ResolveRichPasteRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `ResolveRichPasteResponse`
  引用模型 `ResolveRichPasteResponse`（字段见文末「数据模型」）。
- `422` `application/json` Validation Error → `HTTPValidationError`

### update

#### `GET /api/update/version`

返回当前应用版本号，供前端展示用。 仅返回版本字符串，不请求 GitHub。

**响应**

- `200` `application/json` Successful Response → `object`

#### `GET /api/update/check`

检查是否有新版本。 请求 GitHub API 获取最新 release，与当前版本比较。

**响应**

- `200` `application/json` Successful Response → `object`

#### `GET /api/update/startup-check`

启动阶段自动检查更新；会套用 ignoredReleaseTag 计算 shouldNotify。

**响应**

- `200` `application/json` Successful Response → `object`

#### `PUT /api/update/ignored-tag`

保存当前被用户忽略的 release tag。

**请求体**

Content-Type: `application/json`

引用模型 `IgnoredTagRequest`（字段见文末「数据模型」）。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `DELETE /api/update/ignored-tag`

清空已忽略的 release tag。

**响应**

- `200` `application/json` Successful Response → `object`

#### `POST /api/update/download`

将指定 tag 的源码 zip 下载到 data/update/update.zip。 body: { "tagName": "v0.229" }

**请求体**

Content-Type: `application/json`

类型 `object`。

**响应**

- `200` `application/json` Successful Response → `object`
- `422` `application/json` Validation Error → `HTTPValidationError`

#### `POST /api/update/run`

触发根目录更新脚本。 脚本将：关闭前后端与主终端、解压 data/update/update.zip 覆盖、删除 zip、执行 deploy.bat、退出。

**响应**

- `200` `application/json` Successful Response → `object`

## 数据模型

以下为 OpenAPI 组件模型。`extra` 允许的模型可携带未声明字段。时间戳为 ISO 字符串。

### `ApiPreset`

API预设配置模型 用于存储API预设配置，允许用户保存多组不同的API配置。

- `id`: (string)。Id
- `name`: (string) 默认 "新预设"。Name
- `baseUrl`: (string) 默认 "https://api.openai.com"。Baseurl
- `apiKey`: (string) 默认 ""。Apikey
- `models`: (array<string>)。Models
- `protocol`: (string) 默认 "openai_compatible_chat"。LLM 协议；旧数据缺省映射为 openai_compatible_chat；'auto' 表示按模型识别（T-822）
- `anthropicPromptCache`: (string) 默认 "off"。（旧字段，读兼容）Anthropic prompt cache TTL：off|5m|1h；T-821 起由 promptCache 取代
- `promptCache`: (PromptCacheConfig)。统一 prompt cache 配置（T-821）
- `providerId`: (string | null)。供应商目录 id（T-820）
- `providerParams`: (map<string, string>)。供应商 URL 占位符参数（region/resource/account_id 等）
- `authStyle`: (string | null)。鉴权风格；None 表示按协议默认（T-820-A2）
- `echoReasoning`: (boolean) 默认 true。历史 assistant 消息是否回传 reasoning_content（DeepSeek 带 tools 的请求强制要求；settings.reasoningEchoBack=preset 时生效）
- `presetKind`: (string | null)。预设用途；'tts' 表示 TTS 服务预设
- `ttsProvider`: (string | null)。TTS 服务提供商；仅当 presetKind='tts' 时有意义
- `voiceCatalog`: (array<ApiPresetVoice>)。Voicecatalog
- `ttsGlmLocalRepoPath`: (string | null)。GLM-TTS 仓库根目录（glm_local 专用）
- `ttsGlmLocalPort`: (integer) 默认 8088。GLM-TTS 本地 API 端口（glm_local 专用）
- `ttsGlmLocalManaged`: (boolean) 默认 false。是否由应用托管 GLM-TTS 子进程（glm_local 专用）
- `ttsQwen3LocalRepoPath`: (string | null)。Qwen3-TTS 仓库根目录（qwen3_local 专用）
- `ttsQwen3LocalPort`: (integer) 默认 8080。Qwen3-TTS 本地 FastAPI 网关端口（qwen3_local 专用）
- `ttsQwen3LocalManaged`: (boolean) 默认 false。是否由应用托管 Qwen3-TTS 子进程（qwen3_local 专用）
- `ttsQwen3LocalModelId`: (string | null) 默认 "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"。Qwen3-TTS CustomVoice 网关模型 ID（POST /v1/tts/custom_voice；qwen3_local 专用）
- `ttsQwen3LocalBaseModelId`: (string | null) 默认 "Qwen/Qwen3-TTS-12Hz-1.7B-Base"。Qwen3-TTS Base 网关模型 ID（POST /v1/tts/voice_clone；第二端口子进程；qwen3_local 专用）
- `ttsQwen3LocalVoiceClonePort`: (integer | null)。语音克隆专用网关端口，默认为主端口+1；须与主端口不同（qwen3_local 专用）
- `ttsQwen3LocalDevice`: (string | null) 默认 "cuda:0"。Qwen3-TTS 启动 device（qwen3_local 专用）
- `ttsQwen3LocalDefaultLanguage`: (string | null) 默认 "Auto"。Qwen3-TTS 默认 language 参数（qwen3_local 专用）
- `ttsOmniVoiceLocalRepoPath`: (string | null)。OmniVoice 仓库根目录（omnivoice_local 专用）
- `ttsOmniVoiceLocalPort`: (integer) 默认 8089。OmniVoice 本地 FastAPI 网关端口（omnivoice_local 专用）
- `ttsOmniVoiceLocalManaged`: (boolean) 默认 false。是否由应用托管 OmniVoice 子进程（omnivoice_local 专用）
- `ttsOmniVoiceLocalModelId`: (string | null) 默认 "k2-fsa/OmniVoice"。OmniVoice 启动模型 ID 或本地路径（omnivoice_local 专用）
- `ttsOmniVoiceLocalDevice`: (string | null) 默认 "cuda:0"。OmniVoice 启动 device（omnivoice_local 专用）
- `ttsOmniVoiceLocalDefaultLanguage`: (string | null)。OmniVoice 默认 language 参数（omnivoice_local 专用）

### `ApiPresetVoice`

API 预设内缓存的可选 TTS 音色条目。

- `voiceId`: (string) **必填**。Voiceid
- `name`: (string) **必填**。Name
- `voiceType`: (string) 默认 "system"。Voicetype
- `promptText`: (string | null)。参考音频对应的转写文本（glm_local / omnivoice_local / qwen3_local 语音克隆专用）
- `promptAudioPath`: (string | null)。参考音频本机绝对路径（glm_local / omnivoice_local / qwen3_local 语音克隆专用）
- `instruction`: (string | null)。Qwen3 / OmniVoice 的 instruction / instruct 文本

### `AppendAssistantMessageRequest`

追加助手消息请求

- `role`: (string) 枚举: "system", "user", "assistant", "reasoning" 默认 "assistant"。Role
- `content`: (string) 默认 ""。Content
- `reasoningContent`: (string | null)。Reasoningcontent
- `reasoningDurationSec`: (number | null)。Reasoningdurationsec

### `AppendMessageRequest`

追加消息请求模型 用于向聊天会话追加新消息的请求参数。

- `role`: (string) **必填** 枚举: "system", "user", "assistant"。Role
- `content`: (string) **必填**。Content
- `images`: (array<ChatImageAttachment>)。Images
- `characterId`: (string | null)。Characterid
- `senderPersonaId`: (string | null)。Senderpersonaid
- `senderName`: (string | null)。Sendername
- `senderAvatar`: (string | null)。Senderavatar
- `reasoningContent`: (string | null)。推理/思考链（流式中断落库等场景；通常仅 assistant）
- `reasoningDurationSec`: (number | null)。思考耗时（秒）；可选

### `AssistantAttachment`

助手消息中的附件元数据。

- `id`: (string) **必填**。Id
- `kind`: (string) **必填** 枚举: "image", "text"。Kind
- `storageScope`: (string) **必填** 枚举: "assistant_chat", "workspace_session"。Storagescope
- `storageKey`: (string) **必填**。Storagekey
- `filename`: (string) **必填**。Filename
- `mimeType`: (string) **必填**。Mimetype
- `size`: (integer) **必填**。Size
- `originalName`: (string | null)。Originalname

### `AssistantAttachmentIngestRequest`

- `scope`: (string) **必填**。Scope
- `chatId`: (string | null)。Chatid
- `workspaceSessionId`: (string | null)。Workspacesessionid
- `files`: (array<AssistantAttachmentUploadItem>)。Files

### `AssistantAttachmentIngestResponse`

- `attachments`: (array<AssistantAttachment>)。Attachments
- `workspaceSessionId`: (string | null)。Workspacesessionid

### `AssistantAttachmentUploadItem`

- `fileData`: (string) **必填**。Filedata
- `mimeType`: (string) **必填**。Mimetype
- `originalName`: (string | null)。Originalname

### `AssistantChat`

AI助手聊天记录模型 用于存储AI助手的对话历史。

- `messages`: (array<ChatMessage>)。Messages

### `AssistantSettings`

AI助手设置模型 用于配置AI助手的行为参数。系统提示词由仓库内 app/assistant/AGENT.md 在运行时加载， 不再使用本字段参与推理；prompt 键可仍存在于旧版 JSON 中，已废弃。 API 的 GET/PUT 响应中不包含 prompt。

- `prompt`: (string) 默认 ""。Prompt
- `temperature`: (number | null)。Temperature
- `model`: (string | null)。Model
- `presetId`: (string | null)。Presetid
- `reasoningEffort`: (string | null)。助手思考深度（T-824）；None 沿用全局
- `fastMode`: (boolean | null)。助手 Fast 模式（T-824）
- `context_size`: (integer | null)。上下文总长度限制(token)，0或空表示未启用；最近消息裁剪用
- `tool_read_max_messages`: (integer | null)。助手 chat_read_conversation 最多返回的消息条数；空表示仅受服务端硬上限约束
- `tool_read_max_tokens`: (integer | null)。助手 chat_read_conversation 返回消息列表的最大 token 数（估算）；空表示不启用
- `maxToolTurns`: (integer | null) 默认 8。助手单次请求内允许的最大工具轮次数；空时回退默认值 8
- `maxToolsPerTurn`: (integer | null)。单轮 assistant.tool_calls 最大允许执行数；空表示不额外限制

### `AssistantSettingsUpdate`

AI 助手设置部分更新（PUT 请求体）。 未在 JSON 中出现的字段表示不修改；与已有 AssistantSettings 合并后保存。 prompt 已废弃（系统提示见 app/assistant/AGENT.md）；若仍传入会写入 JSON 但不影响推理。

- `prompt`: (string | null)。Prompt
- `temperature`: (number | null)。Temperature
- `model`: (string | null)。Model
- `presetId`: (string | null)。Presetid
- `reasoningEffort`: (string | null)。助手思考深度（T-824）；显式 null 表示恢复沿用全局
- `fastMode`: (boolean | null)。助手 Fast 模式（T-824）
- `context_size`: (integer | null)。上下文总长度限制(token)，0或空表示未启用；最近消息裁剪用
- `tool_read_max_messages`: (integer | null)。助手 chat_read_conversation 最多返回的消息条数；空表示仅受服务端硬上限约束
- `tool_read_max_tokens`: (integer | null)。助手 chat_read_conversation 返回消息列表的最大 token 数（估算）；空表示不启用
- `maxToolTurns`: (integer | null)。助手单次请求内允许的最大工具轮次数；空表示不修改
- `maxToolsPerTurn`: (integer | null)。单轮 assistant.tool_calls 最大允许执行数；空表示不修改/不限制

### `AssistantStreamRequest`

AI助手流式请求模型

- `userMessage`: (string) **必填**。Usermessage
- `model`: (string | null)。Model
- `temperature`: (number | null)。Temperature
- `appendUserMessage`: (boolean | null) 默认 true。Appendusermessage
- `chatId`: (string | null)。Chatid
- `allowWriteMemory`: (boolean | null)。Allowwritememory
- `allowDestructiveTools`: (boolean | null)。Allowdestructivetools
- `allowWebSearch`: (boolean | null)。Allowwebsearch
- `maxToolTurns`: (integer | null)。Maxtoolturns
- `maxToolsPerTurn`: (integer | null)。Maxtoolsperturn
- `scope`: (string | null)。Scope
- `attachments`: (array<AssistantAttachment>)。Attachments

### `BindMessageReq`

- `chat_id`: (string) **必填**。Chat Id
- `message_id`: (string) **必填**。Message Id
- `asset_id`: (string) **必填**。Asset Id
- `spoken_text`: (string | null)。Spoken Text

### `Body_clone_voice_api_tts_clone_post`

- `baseUrl`: (string) **必填**。Baseurl
- `apiKey`: (string) **必填**。Apikey
- `provider`: (string) 默认 "minimax"。Provider
- `voice_id`: (string) **必填**。Voice Id
- `source_file`: (string) **必填**。Source File
- `model`: (string | null)。Model
- `text`: (string | null)。Text
- `language_boost`: (string | null)。Language Boost
- `prompt_file`: (string | null)。Prompt File
- `prompt_text`: (string | null)。Prompt Text
- `need_noise_reduction`: (boolean) 默认 false。Need Noise Reduction
- `need_volume_normalization`: (boolean) 默认 false。Need Volume Normalization
- `aigc_watermark`: (boolean) 默认 false。Aigc Watermark

### `Body_import_data_api_import_post`

- `file`: (string) **必填**。File

### `Body_import_janitor_character_html_api_import_janitor_character_html_post`

- `file`: (string | null)。File

### `Body_preview_sillytavern_import_api_import_sillytavern_preview_post`

- `file`: (string) **必填**。File

### `Body_upload_font_api_fonts_post`

- `file`: (string) **必填**。File

### `Body_upload_page_background_api_page_backgrounds_post`

- `file`: (string) **必填**。File

### `CharacterCard`

角色卡片模型 用于定义AI角色的完整信息，包括名称、描述、性格、场景等。

- `version`: (integer) 默认 1。Version
- `id`: (string)。Id
- `name`: (string) 默认 "新角色"。Name
- `description`: (string) 默认 ""。Description
- `personality`: (string) 默认 ""。Personality
- `scenario`: (string) 默认 ""。Scenario
- `firstMessage`: (string) 默认 ""。Firstmessage
- `exampleDialogue`: (string) 默认 ""。Exampledialogue
- `systemPrompt`: (string) 默认 ""。Systemprompt
- `avatar`: (string) 默认 ""。Avatar
- `avatarFocusX`: (number | null)。Avatarfocusx
- `avatarFocusY`: (number | null)。Avatarfocusy
- `attachedWorldBookIds`: (array<string>)。Attachedworldbookids
- `extraFirstMessageEntries`: (array<ExtraFirstMessageEntry>)。Extrafirstmessageentries
- `mvuEnabled`: (boolean) 默认 false。Mvuenabled
- `mvuMode`: (string) 枚举: "regex", "directive" 默认 "regex"。Mvumode
- `mvuDirective`: (string | null)。Mvudirective
- `contentRegexRules`: (array<ChatContentRegexRule>)。Contentregexrules
- `initialStateTables`: (array<StatusTableDef>)。新会话初始状态栏定义：创建会话时自动写入 chat.stateVariables.tables，source=chat_assistant
- `createdAt`: (string)。Createdat
- `updatedAt`: (string)。Updatedat

### `Chat`

聊天会话模型 表示一个完整的聊天会话，支持单聊和群聊两种模式。

- `version`: (integer) 默认 1。Version
- `id`: (string)。Id
- `characterId`: (string) **必填**。Characterid
- `title`: (string) 默认 "新对话"。Title
- `messages`: (array<ChatMessage>)。Messages
- `overrides`: (ChatOverrides)
- `userPersonaId`: (string | null)。Userpersonaid
- `isGroup`: (boolean) 默认 false。Isgroup
- `memberIds`: (array<string>)。Memberids
- `memberSettings`: (map<string, GroupMemberSettings>)。Membersettings
- `groupDelay`: (integer) 默认 1500。Groupdelay
- `groupSystemInjectDepth`: (integer) 默认 5 范围 0.0–—。Groupsysteminjectdepth
- `groupSystemAlwaysAtBottom`: (boolean) 默认 true。Groupsystemalwaysatbottom
- `createdAt`: (string)。Createdat
- `updatedAt`: (string)。Updatedat
- `stateVariables`: (StateVariables | null)
- `forkedFromChatId`: (string | null)。消息分叉溯源：源会话 ID
- `forkedFromMessageId`: (string | null)。消息分叉溯源：锚点消息 ID（含该条及之前历史被复制）
- `forkedFromMessageIndex`: (integer | null)。消息分叉溯源：锚点在源会话 messages 中的 1-based 序号（fork 时写入，避免 lineage 加载源会话）

### `ChatContentRegexRule`

会话正文后处理规则。

- `id`: (string)。Id
- `name`: (string | null)。Name
- `enabled`: (boolean) 默认 true。Enabled
- `order`: (integer) 默认 0。Order
- `pattern`: (string) 默认 ""。Pattern
- `action`: (string) 枚举: "remove", "replace", "extract", "extract_and_replace" 默认 "remove"。Action
- `replacement`: (string | null)。Replacement
- `matchMode`: (string) 枚举: "global", "first" 默认 "global"。Matchmode
- `scanDepthOverride`: (integer | null)。Scandepthoverride
- `extractSource`: (string) 枚举: "whole_match", "capture_group" 默认 "whole_match"。Extractsource
- `extractGroupIndex`: (integer | null)。Extractgroupindex

### `ChatImageAttachment`

聊天消息中的图片附件元数据。

- `id`: (string) **必填**。Id
- `filename`: (string) **必填**。Filename
- `mimeType`: (string) **必填**。Mimetype
- `size`: (integer | null)。Size
- `width`: (integer | null)。Width
- `height`: (integer | null)。Height
- `originalName`: (string | null)。Originalname

### `ChatMessage`

聊天消息模型 表示单条聊天消息，支持单聊和群聊场景。

- `version`: (integer) 默认 1。Version
- `id`: (string)。Id
- `role`: (string) **必填** 枚举: "system", "user", "assistant", "tool", "reasoning"。Role
- `content`: (string) **必填**。Content
- `images`: (array<ChatImageAttachment>)。Images
- `attachments`: (array<AssistantAttachment>)。Attachments
- `characterId`: (string | null)。Characterid
- `senderPersonaId`: (string | null)。Senderpersonaid
- `senderName`: (string | null)。Sendername
- `senderAvatar`: (string | null)。Senderavatar
- `ts`: (string)。Ts
- `greetingVariants`: (array<string> | null)。Greetingvariants
- `greetingVariantIndex`: (integer | null)。当前选中的开场/候选正文变体下标（与 greetingVariants 对齐）；避免仅靠 content 反推在重复文案时错位
- `greetingVariantReasoningContents`: (array<string> | null)。与各 greetingVariants 下标一一对应的思考/推理原文（可短于列表时视为尾部为空串）
- `greetingVariantReasoningDurations`: (array<number | null> | null)。与各 greetingVariants 下标一一对应的思考耗时（秒）；可短于列表时视为尾部为 None
- `toolTrace`: (boolean) 默认 false。Tooltrace
- `toolRecord`: (object | null)。Toolrecord
- `tool_call_id`: (string | null)。当 role=tool 时对应 assistant.tool_calls[].id（OpenAI tool_call_id）
- `tool_calls`: (array<object> | null)。当 role=assistant 且本轮需调用工具时，与 OpenAI 返回结构兼容（id/type/function）
- `reasoningContent`: (string | null)。推理/思考链文本（与上游 reasoning_content 对应，持久化用）
- `reasoningDurationSec`: (number | null)。推理/思考耗时（秒，浮点，前端展示为一位小数）；流式路径取首到末 reasoning chunk 的墙钟时间差
- `usage`: (object | null)。本轮归一化用量（T-821）：input/output/cacheRead/cacheWrite tokens
- `ttsAudioAssetId`: (string | null)。已合成的 TTS 音频文件 UUID（对应 data/tts_cache/{uuid}.mp3）
- `ttsAudioSourceText`: (string | null)。实际送入 TTS 合成的文本（含后处理/翻译后的朗读稿）
- `mvuProcessed`: (boolean) 默认 false。MVU 已消费标记：该消息的提取数据已被 MVU Agent 处理；同一会话内最多一条消息持有此标记

### `ChatOverrides`

聊天覆盖设置模型 用于在会话级别覆盖全局设置，优先级高于全局设置。

- `prompt`: (string | null)。Prompt
- `sessionSystemPromptMode`: (string) 枚举: "append", "override" 默认 "append"。Sessionsystempromptmode
- `longTermMemory`: (string | null)。Longtermmemory
- `contextStartMessageId`: (string | null)。Contextstartmessageid
- `contextStartKeepBeforeMessages`: (integer | null)。Contextstartkeepbeforemessages
- `presetId`: (string | null)。Presetid
- `pureAiMode`: (boolean | null)。Pureaimode
- `worldBookIds`: (array<string>)。Worldbookids
- `worldBookAttachments`: (array<WorldBookAttachment>)。Worldbookattachments
- `worldBookGlobalExclusions`: (array<string>)。全局世界书从本会话顺序移除时记录其 ID，生成时不再注入该书
- `contentRegexScanDepthDefault`: (integer) 默认 50 范围 1.0–—。Contentregexscandepthdefault
- `contentRegexRules`: (array<ChatContentRegexRule>)。Contentregexrules
- `contentRegexEnabledByRuleId`: (map<string, boolean>)。Contentregexenabledbyruleid
- `params`: (GenerationParams)
- `draftHelp`: (DraftHelpSettings)
- `tts`: (TtsSessionConfig | null)。会话级 TTS 配置
- `autoMemorySummaryEveryN`: (integer | null)。每隔若干条主会话消息后自动触发助手总结并写入长期记忆；None 或 0 表示关闭
- `lastAutoMemorySummaryAfterMessageId`: (string | null)。上次自动总结成功时锚定的主会话最后一条消息 ID
- `autoMemorySummarySilent`: (boolean) 默认 false。为 True 时不弹窗直接触发；为 False 时先 notify 确认
- `autoMemorySummaryNextAskTier`: (integer) 默认 1 范围 1.0–—。非静默下用户拒绝确认后的倍数（下次在 n*tier 条时再问）
- `mvuModel`: (string | null)。已废弃：MVU 模型改由全局 settings.mvuModel 配置，读档时可能仍存在旧键
- `mvuMode`: (string | null)。会话级 MVU 模式；空值时由上游默认策略决定
- `mvuDirective`: (string | null)。会话级 MVU 指令模式提示词；空白归一为空值
- `groupMvuEnabled`: (boolean | null)。群聊 MVU 总开关；None 表示未显式写入（旧档兼容），True/False 为显式启用或关闭
- `groupMvuAnchorCharacterId`: (string | null)。群聊 MVU 锚定成员角色 ID，须在会话 memberIds 内
- `groupMvuTemplateCharacterId`: (string | null)。沿用或 fork 会话 MVU 时选用的模板成员角色 ID
- `knowledgeGraphEnabled`: (boolean | null)。会话级知识图谱开关；None 视为启用；False 关闭 RP 注入与 MVU 自动维护
- `knowledgeGraphInjectPosition`: (string | null)。RP 注入位置；None 使用 legacy（追加到最后一条 assistant 末尾）
- `knowledgeGraphInjectDepth`: (integer) 默认 5 范围 0.0–—。深度插入时从对话末尾向前计数的条数
- `knowledgeGraphBeforeLastRole`: (string) 枚举: "assistant", "system", "user" 默认 "assistant"。最新消息前模式所锚定的消息角色

### `ChatSearchHit`

- `messageId`: (string) **必填**。Messageid
- `messageIndex`: (integer) **必填**。Messageindex
- `snippet`: (string) **必填**。Snippet

### `ChatSearchResponse`

- `query`: (string) **必填**。Query
- `total`: (integer) **必填**。Total
- `hits`: (array<ChatSearchHit>)。Hits

### `CountTextRequest`

- `text`: (string | null)。Text

### `CreateChatRequest`

创建聊天请求模型 用于创建新聊天会话的请求参数。

- `characterId`: (string) **必填**。Characterid
- `title`: (string | null)。Title
- `userPersonaId`: (string | null)。Userpersonaid
- `isGroup`: (boolean) 默认 false。Isgroup
- `memberIds`: (array<string> | null)。Memberids
- `pureAiMode`: (boolean | null)。Pureaimode
- `memberSettings`: (map<string, GroupMemberSettings> | null)。Membersettings
- `firstMessageCharacterId`: (string | null)。Firstmessagecharacterid
- `groupSystemInjectDepth`: (integer | null)。Groupsysteminjectdepth
- `groupSystemAlwaysAtBottom`: (boolean | null)。Groupsystemalwaysatbottom
- `groupMvuPreset`: (string | null)。Groupmvupreset
- `groupMvuPresetCharacterId`: (string | null)。Groupmvupresetcharacterid
- `mvuMode`: (string | null)。群聊创建时手工指定的会话 MVU 模式；None 表示沿用预设来源 / 默认
- `mvuDirective`: (string | null)。群聊创建时手工指定的会话 MVU 指令；空白归一为 None
- `contentRegexRules`: (array<ChatContentRegexRule> | null)。群聊创建时手工指定的会话级正文正则规则；不传则沿用预设来源 / 默认合并
- `initialStateTables`: (array<StatusTableDef> | null)。群聊创建时手工指定的初始状态栏；不传则沿用预设来源 / 默认

### `DataIntegrityRepairRequest`

- `paths`: (array<string>)。Paths

### `DesignVoiceReq`

- `baseUrl`: (string) **必填**。Baseurl
- `apiKey`: (string) **必填**。Apikey
- `provider`: (string) 枚举: "minimax", "glm", "glm_local", "qwen3_local", "omnivoice_local", "openrouter", "siliconflow" 默认 "minimax"。Provider
- `prompt`: (string) **必填**。Prompt
- `preview_text`: (string) **必填**。Preview Text
- `voice_id`: (string | null)。Voice Id
- `aigc_watermark`: (boolean) 默认 false。Aigc Watermark

### `DraftHelpConversationMessage`

写作辅助临时上下文消息。仅用于本次请求，不写入会话。

- `id`: (string) **必填**。Id
- `role`: (string) **必填** 枚举: "system", "user", "assistant"。Role
- `content`: (string) **必填**。Content
- `characterId`: (string | null)。Characterid
- `senderName`: (string | null)。Sendername

### `DraftHelpRequest`

写作辅助请求模型 mode: - write: 根据当前对话续写一段用户消息 - enhance: 根据草稿润色并扩写

- `chatId`: (string) **必填**。Chatid
- `mode`: (string) **必填** 枚举: "write", "enhance"。Mode
- `draft`: (string | null)。Draft
- `conversation`: (array<DraftHelpConversationMessage> | null)。Conversation

### `DraftHelpSettings`

草稿助手专用设置。

- `context_message_limit`: (integer | null)。草稿助手读取的最近上下文消息条数；0或空表示不单独限制，回退到现有上下文逻辑

### `EmbeddedCharacterCardPreview`

头像 PNG 中内嵌的 ST 角色卡预览（仅解析，不落盘角色/世界书）。

- `card`: (CharacterCard) **必填**
- `worldbook`: (WorldBook | null)

### `ExtraFirstMessageEntry`

额外首句条目：chip 为 True 时在编辑界面显示为矩形 chip。

- `text`: (string) 默认 ""。Text
- `chip`: (boolean) 默认 true。Chip

### `ForkChatRequest`

从此处分叉到新会话的请求体。

- `forkAtMessageId`: (string) **必填**。Forkatmessageid
- `newChatName`: (string | null)。Newchatname

### `ForkLineageResponse`

分叉溯源：来源、兄弟分叉、本会话拉出的子分叉。

- `origin`: (ForkOrigin | null)
- `siblings`: (array<ForkSiblingSummary>)。Siblings
- `outgoingForks`: (array<ForkOutgoingGroup>)。Outgoingforks
- `partialSuccess`: (boolean) 默认 false。Partialsuccess
- `warnings`: (array<ForkLineageWarning>)。Warnings

### `ForkLineageWarning`

- `code`: (string) **必填**。Code
- `message`: (string) **必填**。Message
- `suggestedAction`: (string | null)。Suggestedaction

### `ForkOrigin`

当前会话的分叉来源。

- `chatId`: (string) **必填**。Chatid
- `title`: (string) **必填**。Title
- `messageId`: (string) **必填**。Messageid
- `messageIndex`: (integer) **必填** 范围 1.0–—。1-based index in source messages

### `ForkOutgoingGroup`

从当前会话某条消息拉出的子分叉列表。

- `messageId`: (string) **必填**。Messageid
- `messageIndex`: (integer) **必填** 范围 1.0–—。Messageindex
- `count`: (integer) **必填** 范围 0.0–—。Count
- `chats`: (array<ForkSiblingSummary>)。Chats

### `ForkSiblingSummary`

同源同锚点的平行分叉会话摘要。

- `chatId`: (string) **必填**。Chatid
- `title`: (string) **必填**。Title
- `createdAt`: (string) **必填**。Createdat

### `GenerateStreamRequest`

流式生成请求模型 用于请求流式生成AI回复的请求参数。

- `chatId`: (string) **必填**。Chatid
- `userMessage`: (string) **必填**。Usermessage
- `userImages`: (array<ChatImageAttachment>)。Userimages
- `imageFallbackMode`: (boolean) 默认 false。Imagefallbackmode
- `appendUserMessage`: (boolean | null) 默认 true。Appendusermessage
- `senderPersonaId`: (string | null)。Senderpersonaid
- `senderName`: (string | null)。Sendername
- `senderAvatar`: (string | null)。Senderavatar
- `userPersona`: (UserPersona | null)
- `runtimeOverrides`: (ChatOverrides | null)
- `omitMessageIds`: (array<string>)。仅本次请求拼装 LLM 上下文时忽略的消息 id；不写盘
- `mergeAssistantIntoMessageId`: (string | null)。将本次助手输出作为指定 assistant 消息的新版变体落盘；为空则追加新消息
- `webSearchEnabled`: (boolean) 默认 false。Websearchenabled

### `GenerationParams`

生成参数配置模型 用于配置LLM生成时的参数，包括模型、温度、top_p、最大token数等。 支持通过extra="allow"允许额外字段。

- `model`: (string | null)。Model
- `temperature`: (number | null)。Temperature
- `top_p`: (number | null)。Top P
- `max_tokens`: (integer | null)。Max Tokens
- `context_size`: (integer | null)。上下文总长度限制(token)，0或空表示未启用；长期记忆+最近消息<=此值
- `reasoningEffort`: (string | null)。会话级思考深度（T-824）；None 表示沿用全局 settings.reasoningEffort
- `fastMode`: (boolean | null)。会话级 Fast 模式（T-824）：OpenAI service_tier / Anthropic speed / Gemini service_tier；None 表示关闭

### `GlmLocalActionReq`

- `preset_id`: (string | null)。Preset Id

### `GlmLocalStartReq`

- `preset_id`: (string | null)。Preset Id

### `GroupGenerateRequest`

群聊生成请求模型 用于在群聊中指定某个角色进行回复的请求参数。

- `chatId`: (string) **必填**。Chatid
- `characterId`: (string) **必填**。Characterid
- `imageFallbackMode`: (boolean) 默认 false。Imagefallbackmode
- `runtimeOverrides`: (ChatOverrides | null)
- `omitMessageIds`: (array<string>)。仅本次请求拼装 LLM 上下文时忽略的消息 id；不写盘
- `mergeAssistantIntoMessageId`: (string | null)。将本次助手输出作为指定 assistant 消息的新版变体落盘；为空则追加新消息
- `webSearchEnabled`: (boolean) 默认 false。Websearchenabled

### `GroupMemberSettings`

群聊成员独立设置模型 用于为群聊中的每个成员配置独立的生成参数和行为。

- `model`: (string | null)。Model
- `presetId`: (string | null)。Presetid
- `temperature`: (number | null)。Temperature
- `top_p`: (number | null)。Top P
- `probability`: (number) 默认 1.0 范围 0.0–1.0。Probability
- `includePersonality`: (boolean) 默认 true。Includepersonality
- `includeScenario`: (boolean) 默认 true。Includescenario
- `reasoningEffort`: (string | null)。成员级思考深度（T-831）；None 表示沿用会话 overrides / 全局
- `fastMode`: (boolean | null)。成员级 Fast（T-831）；None 沿用会话，False 显式关闭

### `HTTPValidationError`

- `detail`: (array<ValidationError>)。Detail

### `IgnoredTagRequest`

- `tag`: (string) **必填**。Tag

### `JanitorConfirmRequest`

- `pendingId`: (string) **必填**。Pendingid
- `characterId`: (string) **必填**。Characterid
- `userPersonaId`: (string | null)。Userpersonaid

### `KgEntityUpsertBody`

REST / 手动维护：实体 upsert。

- `name`: (string) **必填**。Name
- `type`: (string) **必填** 枚举: "人物", "地点", "物品", "势力", "事件"。Type
- `properties`: (map<string, string>)。Properties
- `entityId`: (string | null)。Entityid
- `expectedVersion`: (integer | null)。Expectedversion

### `KgRelationDeleteBody`

REST：按三元组删除关系。

- `subjectId`: (string) **必填**。Subjectid
- `predicate`: (string) **必填**。Predicate
- `objectId`: (string) **必填**。Objectid
- `expectedVersion`: (integer | null)。Expectedversion

### `KgRelationUpsertBody`

REST / 手动维护：关系 upsert。

- `subjectId`: (string) **必填**。Subjectid
- `predicate`: (string) **必填**。Predicate
- `objectId`: (string) **必填**。Objectid
- `confidence`: (number) 默认 1.0 范围 0.0–1.0。Confidence
- `expectedVersion`: (integer | null)。Expectedversion

### `ModelCapabilitiesRequest`

- `model`: (string) **必填**。Model
- `providerId`: (string | null)。Providerid
- `baseUrl`: (string | null)。Baseurl

### `OAuthCompletePkceRequest`

- `sessionId`: (string) **必填**。Sessionid
- `callback`: (string) **必填**。Callback

### `OAuthLogoutRequest`

- `presetId`: (string) **必填**。Presetid

### `OAuthSessionRequest`

- `sessionId`: (string) **必填**。Sessionid

### `OAuthStartRequest`

- `presetId`: (string) **必填**。Presetid
- `providerId`: (string | null)。Providerid
- `method`: (string | null)。Method
- `enterpriseUrl`: (string | null)。GitHub Enterprise 域名，空则 github.com

### `OmniVoiceLocalActionReq`

- `preset_id`: (string | null)。Preset Id

### `OmniVoiceLocalStartReq`

- `preset_id`: (string | null)。Preset Id

### `PreprocessReq`

- `text`: (string) **必填**。Text
- `model`: (string) **必填**。Model
- `preset_id`: (string | null)。Preset Id
- `base_url`: (string | null)。Base Url
- `api_key`: (string | null)。Api Key
- `provider`: (string | null)。Provider
- `inject_emotion_tags`: (boolean) 默认 false。Inject Emotion Tags
- `target_language`: (string | null)。Target Language

### `PromoteToGroupRequest`

将单聊复制为群聊：请求体与群聊创建类似，但不插入首句；源单聊保留。

- `title`: (string | null)。Title
- `memberIds`: (array<string>) **必填**。Memberids
- `pureAiMode`: (boolean | null)。Pureaimode
- `userPersonaId`: (string | null)。Userpersonaid
- `memberSettings`: (map<string, GroupMemberSettings> | null)。Membersettings
- `groupSystemInjectDepth`: (integer | null)。Groupsysteminjectdepth
- `groupSystemAlwaysAtBottom`: (boolean | null)。Groupsystemalwaysatbottom

### `PromptCacheConfig`

统一 prompt cache 配置（T-821）。取代仅 Anthropic 的 ``anthropicPromptCache`` 三档。 - mode: auto（按供应商目录推荐）| off | implicit（厂商自动断点）| explicit（显式断点）| best_effort（中国厂商尽力缓存） - ttl: 5m | 1h（Anthropic）| 30m（OpenAI GPT-5.6+）| in_memory | 24h（OpenAI 旧模型）| 秒数（Gemini 显式） - breakpoints: system | tools | history_tail - cacheKey: per_chat | per_character | global | 自定义字符串（OpenAI prompt_cache_key） - explicitMarkers: 百炼/Qwen 消息级 cache_control

- `mode`: (string) 枚举: "auto", "off", "implicit", "explicit", "best_effort" 默认 "auto"。Mode
- `ttl`: (string | integer | null)。Ttl
- `breakpoints`: (array<string>)。Breakpoints
- `cacheKey`: (string | null) 默认 "per_chat"。Cachekey
- `explicitMarkers`: (boolean) 默认 false。Explicitmarkers

### `Qwen3LocalActionReq`

- `preset_id`: (string | null)。Preset Id

### `Qwen3LocalStartReq`

- `preset_id`: (string | null)。Preset Id

### `ResolvePreviewRequest`

T-822：预设编辑器 / 聊天面板预览「这次会怎么发」——不需要 api_key。

- `baseUrl`: (string) 默认 ""。Baseurl
- `model`: (string) 默认 ""。Model
- `protocol`: (string | null)。auto / openai_compatible_chat / ...
- `providerId`: (string | null)。Providerid
- `providerParams`: (map<string, string> | null)。Providerparams
- `promptCache`: (object | null)。Promptcache
- `reasoningEffort`: (string | null)。Reasoningeffort
- `fastMode`: (boolean) 默认 false。Fastmode
- `echoReasoning`: (boolean) 默认 true。Echoreasoning

### `ResolveRichPasteRequest`

- `text`: (string) 默认 ""。粘贴的纯文本
- `html`: (string) 默认 ""。粘贴的 HTML（可能含 file:// 图片）

### `ResolveRichPasteResponse`

- `text`: (string) **必填**。使用的文本（与请求 text 一致，或从 HTML 抽取）
- `images`: (array<ResolvedImage>)。解析出的图片列表

### `ResolvedImage`

- `base64`: (string) **必填**。图片 base64 数据（不含 data:xxx 前缀）
- `mimeType`: (string) **必填**。MIME 类型，如 image/png
- `name`: (string) **必填**。建议文件名，用于前端展示

### `Settings`

全局设置模型 应用的全局配置，包括LLM配置、API预设、生成参数默认值、提示词设置等。

- `version`: (integer) 默认 1。Version
- `llm`: (SettingsLLM)
- `apiPresets`: (array<ApiPreset>)。Apipresets
- `generationDefaults`: (GenerationParams)
- `draftHelpDefaults`: (DraftHelpSettings)
- `prompts`: (SettingsPrompts)
- `streamEnabled`: (boolean) 默认 true。Streamenabled
- `themeId`: (string | null)。Themeid
- `pureAiMode`: (boolean) 默认 false。Pureaimode
- `reasoningEffort`: (string) 枚举: "none", "minimal", "low", "medium", "high", "xhigh", "max" 默认 "none"。Reasoningeffort
- `reasoningEchoBack`: (string) 枚举: "on", "off", "preset" 默认 "preset"。历史思考内容回传：on 总是回传 / off 从不回传 / preset 按 API 预设（或全局连接）开关
- `userPersonas`: (array<UserPersona>)。Userpersonas
- `selectedPersonaId`: (string | null)。Selectedpersonaid
- `selectedFont`: (string | null)。Selectedfont
- `pageBackgroundImage`: (string | null)。Pagebackgroundimage
- `pageBackgroundOpacity`: (number | null)。Pagebackgroundopacity
- `pageBackgroundBlurPx`: (number | null)。Pagebackgroundblurpx
- `webgpuBackgroundEnabled`: (boolean) 默认 false。Webgpubackgroundenabled
- `webgpuBackgroundPresets`: (array<WebGpuBackgroundPreset>)。Webgpubackgroundpresets
- `webgpuBackgroundActivePresetId`: (string | null)。Webgpubackgroundactivepresetid
- `webgpuBackgroundTargetFps`: (integer) 默认 60 范围 12.0–120.0。Webgpubackgroundtargetfps
- `messageFontSize`: (integer | null)。Messagefontsize
- `ttsEnabled`: (boolean) 默认 false。Ttsenabled
- `ttsAudioCacheLimitMb`: (integer) 默认 200 范围 10.0–10000.0。Ttsaudiocachelimitmb
- `worldBookEntryScanDepthDefault`: (integer) 默认 2。Worldbookentryscandepthdefault
- `contentRegexRuleLibrary`: (array<ChatContentRegexRule>)。Contentregexrulelibrary
- `mvuModel`: (string | null)。全局 MVU Agent / 导入期 MVU Agent 专用模型名；空值时回退 llm.defaultModel 与 modelCandidates
- `webSearch`: (WebSearchSettings | null)
- `createdAt`: (string)。Createdat
- `updatedAt`: (string)。Updatedat

### `SettingsLLM`

LLM配置模型 用于配置LLM API的连接信息和模型选择。

- `baseUrl`: (string) 默认 "https://api.openai.com"。Baseurl
- `apiKey`: (string) 默认 ""。Apikey
- `defaultModel`: (string) 默认 ""。Defaultmodel
- `modelCandidates`: (array<string>)。Modelcandidates
- `usedModels`: (array<string>)。Usedmodels
- `protocol`: (string) 默认 "openai_compatible_chat"。LLM 协议；缺省 openai_compatible_chat（T-805）
- `anthropicPromptCache`: (string) 默认 "off"。（旧字段，读兼容）Anthropic prompt cache TTL：off|5m|1h；T-821 起由 promptCache 取代
- `promptCache`: (PromptCacheConfig)。统一 prompt cache 配置（T-821）
- `providerId`: (string | null)。供应商目录 id（T-820）
- `providerParams`: (map<string, string>)。供应商 URL 占位符参数（region/resource/account_id 等）
- `authStyle`: (string | null)。鉴权风格；None 表示按协议默认（T-820-A2）
- `echoReasoning`: (boolean) 默认 true。全局连接：历史 assistant 消息是否回传 reasoning_content（settings.reasoningEchoBack=preset 时生效）

### `SettingsPrompts`

提示词设置模型 用于存储全局系统提示词配置。

- `globalSystem`: (string) 默认 ""。Globalsystem
- `globalPrefill`: (string) 默认 ""。Globalprefill
- `globalPrefillEnabled`: (boolean) 默认 true。Globalprefillenabled

### `ShaderPresetDiagnosticItem`

WGSL 诊断条目（与前端 WgslDiagnostic 对齐；服务端无编译器时通常为空列表）。

- `severity`: (string) 枚举: "error", "warning", "info" 默认 "error"。Severity
- `message`: (string) **必填**。Message
- `line`: (integer | null)。Line
- `column`: (integer | null)。Column
- `length`: (integer | null)。Length

### `ShaderPresetMutationResponse`

创建/保存着色器预设后的统一响应（含可扩展 diagnostics 占位）。

- `ok`: (boolean) 默认 true。Ok
- `filename`: (string) **必填**。Filename
- `normalized`: (boolean) 默认 true。Normalized
- `diagnostics`: (array<ShaderPresetDiagnosticItem>)。Diagnostics
- `note`: (string | null) 默认 "服务端仅做规范化与存储校验，WGSL 语法编译诊断以浏览器 WebGPU 为准。"。Note

### `ShaderPresetUpdateRequest`

- `source`: (string) **必填**。Source

### `SillyTavernConfirmRequest`

- `pendingId`: (string) **必填**。Pendingid
- `enableMvuCompatibility`: (boolean) 默认 false。Enablemvucompatibility
- `mvuMode`: (string) 枚举: "regex", "directive" 默认 "regex"。Mvumode

### `SillyTavernMaterializeRequest`

由预览 pending 生成角色卡与世界书数据（不落库），供头像嵌入卡编辑合并等场景。

- `pendingId`: (string) **必填**。Pendingid
- `enableMvuCompatibility`: (boolean) 默认 false。Enablemvucompatibility
- `mvuMode`: (string) 枚举: "regex", "directive" 默认 "regex"。Mvumode
- `avatarFilename`: (string | null)。Avatarfilename

### `SingleInterjectRequest`

单次插话请求模型 用于在群聊轮次结束后让某个角色额外回复一次的请求参数。

- `chatId`: (string) **必填**。Chatid
- `characterId`: (string) **必填**。Characterid
- `imageFallbackMode`: (boolean) 默认 false。Imagefallbackmode
- `omitMessageIds`: (array<string>)。仅本次请求拼装 LLM 上下文时忽略的消息 id；不写盘
- `mergeAssistantIntoMessageId`: (string | null)。将本次助手输出作为指定 assistant 消息的新版变体落盘；为空则追加新消息
- `webSearchEnabled`: (boolean) 默认 false。Websearchenabled

### `StateVariables`

会话级 MVU 状态变量快照，存于 chat.json 内嵌。

- `version`: (integer) 默认 1。Version
- `updatedAt`: (string) 默认 ""。Updatedat
- `source`: (string) 枚举: "mvu_agent", "chat_assistant" 默认 "mvu_agent"。Source
- `tables`: (array<StatusTableDef>)。Tables

### `StatusTableDef`

MVU 状态表格定义。

- `name`: (string) **必填**。Name
- `columns`: (array<string>)。Columns
- `rows`: (array<StatusTableRow>)。Rows

### `StatusTableRow`

MVU 状态表格行。

- `field`: (string) **必填**。Field
- `cells`: (map<string, string>)。Cells

### `SynthesizeReq`

- `text`: (string) **必填**。Text
- `content_text`: (string | null)。Content Text
- `voice_id`: (string) **必填**。Voice Id
- `model`: (string) 默认 "speech-2.8-hd"。Model
- `speed`: (number) 默认 1.0 范围 0.5–2.0。Speed
- `volume`: (number) 默认 1.0 范围 —–10.0。Volume
- `pitch`: (integer) 默认 0 范围 -12.0–12.0。Pitch
- `emotion`: (string | null)。Emotion
- `audio_format`: (string) 默认 "mp3"。Audio Format
- `sample_rate`: (integer) 默认 32000。Sample Rate
- `stream`: (boolean) 默认 false。Stream
- `message_id`: (string | null)。Message Id
- `chat_id`: (string | null)。Chat Id
- `preset_id`: (string | null)。Preset Id

### `TestModelsRequest`

测试指定 API 配置的可用模型列表。

- `baseUrl`: (string) **必填**。Baseurl
- `apiKey`: (string) **必填**。Apikey
- `protocol`: (string | null)。LLM 协议；缺省 openai_compatible_chat；auto 时按 base_url 所属厂商推断
- `providerId`: (string | null)。T-820：名录厂商 id，用于 auto 协议与 URL 模板
- `providerParams`: (map<string, string> | null)。URL 模板占位参数（如 Azure resource）
- `presetId`: (string | null)。T-830：用已保存预设（含 OAuth token）列模型
- `authStyle`: (string | null)。Authstyle

### `TestVoicesReq`

- `baseUrl`: (string) **必填**。Baseurl
- `apiKey`: (string) **必填**。Apikey
- `provider`: (string) 枚举: "minimax", "glm", "glm_local", "qwen3_local", "omnivoice_local", "openrouter", "siliconflow" 默认 "minimax"。Provider
- `voice_type`: (string) 默认 "all"。Voice Type

### `TtsSessionConfig`

会话级 TTS 配置，存于 ChatOverrides.tts。

- `autoReadScope`: (string) 枚举: "off", "assistant_only", "user_only", "all" 默认 "off"。Autoreadscope
- `readGapSeconds`: (number) 默认 0.0 范围 0.0–—。Readgapseconds
- `model`: (string | null)。Model
- `voiceByCharacterId`: (map<string, string>)。Voicebycharacterid
- `voiceByPersonaId`: (map<string, string>)。Voicebypersonaid
- `presetId`: (string | null)。Presetid
- `preprocessEnabled`: (boolean) 默认 false。Preprocessenabled
- `preprocessModel`: (string | null)。Preprocessmodel
- `preprocessPresetId`: (string | null)。Preprocesspresetid
- `preprocessTargetLanguage`: (string | null)。Preprocesstargetlanguage
- `injectEmotionTags`: (boolean) 默认 false。Injectemotiontags

### `UpdateChatRequest`

更新聊天请求模型 用于更新聊天会话信息的请求参数。

- `title`: (string | null)。Title
- `overrides`: (ChatOverrides | null)
- `groupDelay`: (integer | null)。Groupdelay
- `memberSettings`: (map<string, GroupMemberSettings> | null)。Membersettings
- `memberIds`: (array<string> | null)。Memberids
- `userPersonaId`: (string | null)。Userpersonaid
- `groupSystemInjectDepth`: (integer | null)。Groupsysteminjectdepth
- `groupSystemAlwaysAtBottom`: (boolean | null)。Groupsystemalwaysatbottom
- `stateVariables`: (StateVariables | null)。群聊设置弹窗等场景一次性更新初始状态栏；None 表示清空

### `UpdateMessageRequest`

更新消息请求模型 用于更新聊天会话中已有消息的请求参数。

- `role`: (string) **必填** 枚举: "system", "user", "assistant"。Role
- `content`: (string) **必填**。Content
- `images`: (array<ChatImageAttachment> | null)。Images
- `characterId`: (string | null)。Characterid
- `senderPersonaId`: (string | null)。Senderpersonaid
- `senderName`: (string | null)。Sendername
- `senderAvatar`: (string | null)。Senderavatar
- `greetingVariantIndex`: (integer | null)。Greetingvariantindex
- `greetingVariants`: (array<string> | null)。多候选正文列表；不发送则不修改。显式 null 或空列表则清除多版本元数据
- `greetingVariantReasoningContents`: (array<string> | null)。与 greetingVariants 等长的每候选思考文；不发送则不修改。随 clearing 时一并可清
- `greetingVariantReasoningDurations`: (array<number | null> | null)。与 greetingVariants 等长的每候选思考耗时（秒）
- `reasoningContent`: (string | null)。补写或修正推理/思考链文本（如流式中断后落库）
- `reasoningDurationSec`: (number | null)。补写思考耗时（秒）

### `UploadAvatarRequest`

头像上传请求模型 接受base64编码的图片数据，支持data URL格式。

- `imageData`: (string) **必填**。Imagedata
- `filename`: (string | null)。Filename

### `UploadAvatarResponse`

头像上传响应模型

- `filename`: (string) **必填**。Filename
- `embeddedCharacterCard`: (EmbeddedCharacterCardPreview | null)

### `UploadChatImageItem`

- `imageData`: (string) **必填**。Imagedata
- `mimeType`: (string) 默认 "image/png"。Mimetype
- `originalName`: (string | null)。Originalname
- `width`: (integer | null)。Width
- `height`: (integer | null)。Height

### `UploadChatImagesRequest`

- `images`: (array<UploadChatImageItem>)。Images

### `UploadChatImagesResponse`

- `images`: (array<ChatImageAttachment>)。Images

### `UserPersona`

用户Persona模型 用于定义用户的身份和特征，在对话中会注入到系统提示词中。

- `id`: (string)。Id
- `name`: (string) 默认 "新用户"。Name
- `description`: (string) 默认 ""。Description
- `avatar`: (string) 默认 ""。Avatar
- `createdAt`: (string)。Createdat
- `updatedAt`: (string)。Updatedat

### `ValidationError`

- `loc`: (array<string | integer>) **必填**。Location
- `msg`: (string) **必填**。Message
- `type`: (string) **必填**。Error Type
- `input`: (any)。Input
- `ctx`: (object)。Context

### `VoicesReq`

- `voice_type`: (string) 默认 "all"。Voice Type

### `WebGpuBackgroundPreset`

WebGPU 背景预设元数据。 仅保存元数据，WGSL 源文件本体存于 data/shader_presets。

- `id`: (string)。Id
- `name`: (string) 默认 "新建 WebGPU 预设"。Name
- `wgslFile`: (string) **必填**。Wgslfile

### `WebSearchBochaSettings`

博查 Web Search 请求参数（POST /v1/web-search；count 1–50 以正文说明为准）。

- `apiKey`: (string) 默认 ""。Apikey
- `baseUrl`: (string) 默认 "https://api.bocha.cn"。Baseurl
- `count`: (integer | null)。Count
- `freshness`: (string | null)。Freshness
- `summary`: (boolean | null)。Summary
- `include`: (string | null)。Include
- `exclude`: (string | null)。Exclude

### `WebSearchSettings`

主聊天网络搜索：按 provider 选择 Tavily 或博查，嵌套字段与各厂商 Search API 一致。

- `provider`: (string) 枚举: "tavily", "bocha" 默认 "tavily"。Provider
- `tavily`: (WebSearchTavilySettings | null)
- `bocha`: (WebSearchBochaSettings | null)

### `WebSearchTavilySettings`

Tavily Search 请求参数（与官方 POST /search 对齐；apiKey 存于本地设置）。

- `apiKey`: (string) 默认 ""。Apikey
- `max_results`: (integer | null)。Max Results
- `search_depth`: (string | null)。Search Depth
- `topic`: (string | null)。Topic
- `include_answer`: (boolean | string | null)。Include Answer
- `include_raw_content`: (boolean | string | null)。Include Raw Content
- `time_range`: (string | null)。Time Range
- `start_date`: (string | null)。Start Date
- `end_date`: (string | null)。End Date
- `include_domains`: (array<string> | null)。Include Domains
- `exclude_domains`: (array<string> | null)。Exclude Domains
- `chunks_per_source`: (integer | null)。Chunks Per Source
- `include_images`: (boolean | null)。Include Images
- `include_image_descriptions`: (boolean | null)。Include Image Descriptions
- `include_favicon`: (boolean | null)。Include Favicon

### `WorkspaceSessionCleanupRequest`

- `sessionId`: (string) **必填**。Sessionid

### `WorldBook`

- `id`: (string)。Id
- `name`: (string) **必填**。Name
- `entries`: (array<WorldBookEntry>)。Entries
- `globalActive`: (boolean) 默认 false。Globalactive
- `sessionChatIds`: (array<string>)。Sessionchatids
- `createdAt`: (string)。Createdat
- `updatedAt`: (string)。Updatedat

### `WorldBookAttachment`

会话内绑定的一本世界书及其扫描/插入深度（与条目内字段解耦）。

- `worldBookId`: (string) **必填**。Worldbookid
- `scanDepth`: (integer | null)。Scandepth
- `insertDepth`: (integer) 默认 5 范围 1.0–—。Insertdepth

### `WorldBookEntry`

条目不再包含扫描/插入深度；深度由会话 ChatOverrides.worldBookAttachments 提供。

- `id`: (string)。Id
- `title`: (string) 默认 ""。Title
- `regex`: (string) 默认 ""。Regex
- `content`: (string) 默认 ""。Content
- `enabled`: (boolean) 默认 true。Enabled
- `orderIndex`: (integer) 默认 0。Orderindex

