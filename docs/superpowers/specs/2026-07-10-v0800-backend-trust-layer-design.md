# v0.800 后端可信执行层设计

- status: draft
- version: v0.800
- scope: fast-fail、协议适配、计量账本、成本统计、搜索供应商、性能与健壮性
- non_goal: 本文不授权直接编码；实施按 T-801～T-814 分批

## 1. 设计原则

### 1.1 无静默失败

任何会改变用户结果的失败都必须满足：

1. 有稳定错误 code。
2. 有用户可读 message。
3. 有开发定位 detail/requestId/source。
4. 明确是否可重试。
5. 到达前端错误栈或对应设置面板。
6. 不返回空数组、空正文、默认模型或 `ok=true` 冒充成功。

### 1.2 无静默 fallback

- 默认不切换模型、协议、供应商。
- 显式 fallback 必须是用户配置项，并在结果元数据中记录：
  - `fallbackApplied`
  - `fallbackFrom`
  - `fallbackTo`
  - `fallbackReason`
- 回退结果在 UI 中可见；统计按实际请求模型/供应商记账。

### 1.3 云端事实优先

usage/cost 优先级：

1. 供应商响应中的 `cost` / billing 字段。
2. 供应商响应中的 token/cache usage + 本地价格表。
3. 本地 tokenizer 估算（仅标记 `estimated`，不得显示为云端精确值）。
4. 无法可靠计算时显示“未知”，不得填 0。

## 2. 错误模型

```python
class AppError:
    code: str
    message: str
    detail: str | None
    source: str
    retryable: bool
    request_id: str
    provider: str | None
    protocol: str | None
    upstream_status: int | None
    suggested_action: str | None
```

### 2.1 分层

| 层 | 示例 code |
|----|-----------|
| 配置 | `config_missing`, `provider_protocol_mismatch` |
| 鉴权/配额 | `provider_auth_failed`, `provider_quota_exceeded` |
| 网络 | `upstream_timeout`, `upstream_unreachable`, `stream_interrupted` |
| 协议 | `provider_response_invalid`, `stream_event_invalid`, `tool_call_invalid` |
| 存储 | `data_not_found`, `data_corrupted`, `file_lock_timeout`, `atomic_write_failed` |
| 业务 | `chat_not_found`, `invalid_generation_state`, `tool_limit_exceeded` |
| 后台任务 | `daemon_failed`, `subprocess_failed`, `cleanup_failed` |

### 2.2 REST/SSE

- REST 失败使用对应 4xx/5xx；响应体包含统一错误对象。
- SSE：
  - `event:meta`：requestId、provider、protocol、resolvedModel。
  - `event:reasoning` / `event:delta` / `event:tool`。
  - `event:usage`：供应商返回 usage 时立即发送，可在 done 前出现。
  - `event:done`：仅成功发送，包含持久化后的 messageId 与 generation metadata。
  - `event:error`：仅失败发送，`terminal=true`，之后关闭流。
- 前端不得依据字符串匹配判断错误类型。

## 3. 协议内核

### 3.1 Provider Adapter

每个适配器实现统一接口：

```text
validate_config()
list_models()
build_request(canonical_messages, tools, generation_config)
complete()
stream()
decode_message()
decode_tool_calls()
decode_usage()
decode_error()
```

### 3.2 首批协议

| provider/protocol | 非流 | 流式 | 工具 | usage | 缓存 |
|-------------------|------|------|------|-------|------|
| OpenAI-compatible Chat Completions | ✅ 迁移现有 | ✅ | OpenAI tool_calls | provider-dependent | provider-dependent |
| OpenAI Responses | 新增 | 新增 | Responses tools/items | 原生 usage | 按官方字段 |
| Anthropic Messages | 新增 | 新增 | tool_use/tool_result | input/output/cache | 显式 prompt caching |
| Gemini generateContent | 新增 | 新增 | functionCall/functionResponse | usageMetadata | cached content/官方能力 |

### 3.3 Canonical Message

协议内核内部使用规范结构，不把 OpenAI 字段直接扩散到业务层：

```text
role: system | developer | user | assistant | tool
contentParts: text | image | toolCall | toolResult | reasoning
providerMessageId?
toolCalls[]
toolResult?
cacheControl?
metadata?
```

适配器负责：

- system/developer 指令映射。
- 图片与附件格式。
- assistant prefill 支持能力检查。
- 工具调用 ID、参数增量与结果回填。
- 流式 finish reason 与断流检测。
- 不支持能力时 fast-fail `provider_capability_unsupported`，不得删字段继续。

## 4. Anthropic 显式缓存

API 预设新增（命名实施时可调整）：

```text
protocol: anthropic_messages
anthropicPromptCacheEnabled: boolean = false
```

- 仅 Anthropic Messages 协议显示开关。
- 默认关闭，用户显式开启。
- 首批缓存边界：稳定 system prompt / tools schema；世界书等动态块需稳定性评估后再纳入。
- 请求 metadata 记录缓存开关与实际 cache usage。
- 若上游不支持或返回缓存配置错误，直接报错，不静默重发无缓存请求。

## 5. Generation Metadata

### 5.1 消息级来源

assistant 消息新增：

```json
{
  "generationMetadata": {
    "version": 1,
    "requestId": "req_xxx",
    "provider": "anthropic",
    "protocol": "anthropic_messages",
    "requestedModel": "Claude Opus 4.x",
    "resolvedModel": "claude-opus-4-1",
    "startedAt": "ISO-8601",
    "firstTokenLatencyMs": 812,
    "totalDurationMs": 6400,
    "usage": {
      "inputTokens": 1200,
      "outputTokens": 380,
      "cacheReadInputTokens": 900,
      "cacheWriteInputTokens": 0,
      "reasoningTokens": null,
      "totalTokens": 1580
    },
    "cost": {
      "amount": 0.0312,
      "currency": "USD",
      "source": "provider",
      "providerAmount": 0.0312,
      "estimatedAmount": 0.0308,
      "pricingRuleId": "anthropic-claude-opus-4-1@2026-07"
    },
    "calls": []
  }
}
```

一个最终消息可能包含多次模型调用（工具轮次、搜索轮次），因此：

- 顶层为聚合值。
- `calls[]` 保存每次上游请求的精简 usage/timing/cost/providerRequestId。
- 不在消息中保存 API Key、完整请求正文或敏感 header。

### 5.2 TTFT 与总耗时

- `startedAt`：请求即将发往上游。
- `firstTokenLatencyMs`：首个正文或 reasoning chunk 到达；非流式可记首个完整响应时间并标注 `nonStreaming=true`。
- `totalDurationMs`：上游请求开始到解析/usage 完成。
- 另保留持久化耗时与工具耗时到 trace，不混入 provider total。

## 6. Usage Ledger

为避免每次统计扫描全部 chat JSON，新增 append-only ledger（实施时确定路径）：

```text
data/usage/YYYY-MM.jsonl
data/usage_index.json
```

每个 event：

- `eventId`（幂等键）
- `requestId`
- `chatId`
- `messageId`
- `provider/protocol/requestedModel/resolvedModel`
- normalized usage/cost/timing
- `status: completed|failed|cancelled`
- 时间戳

原则：

- API 调用产生的实际成本不会因消息编辑/删除而消失。
- 会话统计按 ledger 的 `chatId` 过滤，表达“该会话已发生的 API 消耗”。
- 全局统计为所有 ledger 事件。
- 重放/重试必须使用新的 requestId；同一 eventId 重复写入需去重。
- ledger 写失败不能让已完成消息伪装为完整成功：返回 `usage_persist_failed`，并保留可修复队列。

## 7. 定价引擎

### 7.1 规则优先级

1. 云端 cost：直接计入，不被本地估算覆盖。
2. resolvedModel 精确 ID。
3. provider + 官方模型别名。
4. 版本化正则 alias。
5. 用户手工映射。
6. 未匹配：cost unknown。

### 7.2 避免错误计费

“克”“克劳德”等宽泛关键词可能命中多个 Claude 家族，**不得仅凭单字自动映射到某个真实模型**。可以作为候选提示，但只有在能确定 family/tier/version，或用户手工确认后才应用价格。

价格表字段：

- provider/canonicalModelId
- aliases / regexAliases
- effectiveFrom / effectiveTo
- inputPerMillion
- outputPerMillion
- cacheReadPerMillion
- cacheWritePerMillion
- currency
- sourceUrl / updatedAt

价格变动时不重算历史 cloud cost；本地估算保留 `pricingRuleId`，支持可选重新估算视图。

## 8. 统计 API 与 UI

### 8.1 API

```text
GET /api/usage/summary?scope=chat&chatId=...
GET /api/usage/summary?scope=global
GET /api/usage/models?scope=...
GET /api/usage/events?...（可分页）
GET /api/pricing/rules
PUT /api/pricing/rules/...（本地覆盖）
```

汇总字段：

- 总输入 token
- 总输出 token
- 平均输入 / 平均输出（以 completed billable call 为分母）
- 缓存读取输入 token
- 缓存写入输入 token
- 缓存命中率
- 总成本
- provider cost / local estimated cost / unknown cost 分项
- 请求数、成功/失败/取消数
- 平均 TTFT、P50/P95 TTFT、平均总耗时
- 按 provider/protocol/model 分组

缓存命中率必须由 adapter 按供应商语义归一化，并保留原始 usage；不得把供应商定义不同的字段直接相加。

### 8.2 设置页位置

组件：`frontend/src/components/settings-drawer/SettingsDrawerGlobalAppSection.vue`

位置：`应用与更新` accordion 内容区内，**成本计算器按钮上方**。

建议拆分：

```text
SettingsDrawerGlobalUsageSummary.vue
  ├─ scope switch：当前会话 | 全局
  ├─ summary cards：token / cache / cost / latency
  ├─ model table：按模型汇总
  ├─ cost source legend：云端 | 本地估算 | 未知
  └─ refresh / time range
```

- 无活动会话时禁用“当前会话”，并明确原因。
- 金额使用统一 currency；非 USD 云端 cost 保留 raw currency，换算需显式汇率来源，否则分币种展示。
- “成本计算器”外链保留，位于统计组件下方。

## 9. 网络搜索扩展

分两类：

### 9.1 独立搜索 API

- 已有：Tavily、博查。
- 候选：Exa、Brave Search、Serper/SerpAPI 等。
- 接入前必须核对官方 API、可用地区、计费、配额和 ToS。

### 9.2 模型供应商原生联网

- OpenAI Responses web search tool。
- Anthropic web search tool。
- Gemini Google Search grounding。

原生联网随协议 adapter 走，不伪装为通用 `web_search` 函数。UI 应区分：

- “独立搜索供应商”
- “模型原生联网能力”

策略：

- 每次只启用用户选中的 provider。
- 失败不自动切换。
- quota/auth/timeout/内容过滤分别报错。
- 搜索调用也进入 usage/cost/latency ledger。

## 10. 性能与健壮性

### 10.1 先建立基线

- chat 列表/加载/写入 P50/P95。
- 单聊、群聊、工具轮次的后端额外开销。
- TTFT 与 provider total 分离。
- MVU、知识图谱、正文正则、TTS 各自耗时。
- 启动扫描与数据完整性扫描耗时。

### 10.2 优化候选

- 共享 `httpx.AsyncClient`、连接池与显式 timeout policy。
- chatId/fork/usage 索引，避免全目录重复扫描。
- JSON 读取缓存按 mtime/size 校验；写入保持 portalocker + 原子替换。
- 流式解析避免逐字符服务端拆分造成过多调度（需用基准确定 chunk 策略）。
- 大型 import/export 使用流式/批量处理。
- TTS 子进程生命周期与缓存索引。
- 后台 sweeper/daemon 失败持久化、退避和健康状态。

### 10.3 稳健性测试

- 上游 401/403/429/5xx。
- connect/read/total timeout。
- SSE 半包、非法 JSON、未知事件、无 finish、断流。
- 工具调用参数分片、重复 ID、缺失结果。
- 文件锁超时、磁盘满、部分写、损坏索引。
- usage 有/无/cost 有/无/缓存字段差异。
- 请求完成但 metadata/ledger 写失败。

## 11. 迁移与兼容

- `ChatMessage.model_config(extra="allow")` 可读取旧消息；新增字段必须可选且 versioned。
- 旧 API preset 默认映射为 `openai_compatible_chat`，但保存时显式写 protocol。
- 迁移只做结构转换，不测试上游时不得宣称配置有效。
- 旧错误字符串前端兼容期保留一版，但新后端入口必须输出统一错误体。
- 所有迁移写入 warning，禁止静默修复损坏配置。
