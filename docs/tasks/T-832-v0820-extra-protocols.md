# T-832 v0.820 Bedrock / Mistral / Vertex 原生协议（P1，可滑动）

- status: **implemented，独立黑盒检查已通过（2026-11-08，`tools/api-check` t832 171 项通过 169，另 2 项规格未定义），待作者 Vertex 实测**；Bedrock 和 Mistral 只有模拟验证
- area: `backend/app/llm/providers/`
- priority: P1
- depends_on: T-820-A2（Bedrock Anthropic invoke 变体已有；eventstream 仍 fast-fail）

## 目标

- AWS Bedrock Converse + 原生 `invoke-with-response-stream` eventstream 解析。
- Mistral Conversations API。
- Vertex Anthropic `rawPredict`。

Bedrock eventstream 的 fast-fail 已移除。

## 实现说明

### 协议和文件

| 能力 | 协议 / 鉴权 | 文件 |
|------|------------|------|
| Bedrock Converse | `bedrock_converse`，Bearer | `backend/app/llm/providers/bedrock_converse.py` |
| eventstream 帧解析（CRC 校验、异常帧转统一错误） | Converse 和 invoke 共用 | `backend/app/llm/aws_eventstream.py` |
| Mistral Conversations | `mistral_conversations`，Bearer | `backend/app/llm/providers/mistral_conversations.py` |
| Vertex Anthropic | `anthropic_messages` + `vertex_service_account` | `backend/app/llm/vertex_auth.py`、`providers/anthropic_messages.py` |

目录 overlay 新增 `amazon-bedrock-converse`、`mistral-conversations`、`vertex-anthropic`。

### 能力矩阵

| | Bedrock Converse | Mistral Conversations | Vertex Anthropic |
|---|---|---|---|
| 非流式 / 流式 | 支持 | 支持 | 支持 |
| 工具 | toolUse / toolResult；`tool_choice=none` fast-fail | function.call / function.result；指定具体工具 fast-fail | 同 Anthropic |
| 推理 | 只支持 Claude，按模型表选写法；其他模型设了深度就 fast-fail | `completion_args.reasoning_effort`，按模型表；未知模型设了深度就 fast-fail | 按模型表选写法 |
| 缓存 | 显式写 `cachePoint`（Claude、Nova）；其他模型 fast-fail；自动模式不发 | 请求体没有缓存字段；显式 fast-fail | `cache_control`，同 Anthropic |
| 图片 | fast-fail | fast-fail | fast-fail（沿用） |
| Fast | fast-fail | fast-fail | fast-fail（Google 托管版没有） |
| 模型列表 | `GET /foundation-models`（主机由 `bedrock-runtime.` 换成 `bedrock.`） | `GET /v1/models` | fast-fail（没有 Models API），手动添加 |
| 网页抓取工具 | 不适用 | 不适用 | fast-fail（Google 托管版没有） |

### 密钥

- `GET /api/settings`、`PUT /api/settings` 的响应和 `/api/settings/backup` 里，服务账号 JSON 的 `private_key` 换成占位值。写回时按预设 id 和 `client_email`、`private_key_id` 从已保存的设置还原。
- 备份不含私钥，恢复后要重新粘贴，否则使用时报 `config_invalid`。
- token 交换的请求体和响应体不进 HTTP 日志，只记状态码。token 只在内存里缓存，距过期 5 分钟内刷新，Vertex 返回 401 时作废。
- 服务账号 JSON 配其他鉴权或协议时在 `preset_resolve` 和 `/api/llm/test-models` 直接拒绝，不会当普通密钥发出去。

### 已知限制

- Converse 的带签名 reasoning 块按 `toolUseId` 保留在进程内存里（最多 512 组），重启后丢失。旧版手动思考模型的工具续轮会由上游报错；官方说明自适应思考的模型不要求轮次以 thinking 块开头。
- 协议下拉的选项表 `constants/llmProtocols.ts` 不在本任务范围，新协议由预设编辑器自己追加。全局连接区的下拉没有新协议。
- 选了目录条目且填了供应商参数时，地址按模板生成，手改 Base URL 不生效（沿用 T-820 的规则）。
