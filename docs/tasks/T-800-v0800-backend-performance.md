# T-800 v0.800 后端 Fast-Fail、性能、原生协议与计量总卡

- status: in-progress（实施阶段；T-801 已完成）
- area: backend 全域 + 必要前端配套
- theme: **无静默失败、可定位错误、全链路性能与健壮性、原生多厂商协议、精确用量与成本**
- version_note: 文档宣布进入 v0.800；`backend/app/version.py` 仍保持 `v0.700`，直到首批实现与发布门禁完成

## v0.800 北极星

v0.800 从“后端性能版”升级为“**后端可信执行层**”：

1. **全后端 Fast-Fail**：业务错误、配置错误、上游协议错误、存储错误不得静默吞掉，不得伪装为空结果或成功。
2. **取消静默 fallback**：自动换模型、候选模型兜底、协议猜测、供应商切换、解析失败后继续等行为默认禁止。
3. **错误必须可感知**：REST、SSE、后台任务、工具调用都返回统一结构化错误；前端进入错误栈并给出可操作提示。
4. **性能与健壮性并重**：先测量，再优化；所有 backend 组件纳入覆盖矩阵，不只优化生成路由。
5. **原生协议成为一等能力**：OpenAI Chat Completions 兼容层继续保留，同时新增 OpenAI Responses、Anthropic Messages、Gemini 原生适配。
6. **云端数据优先计量**：token、缓存、cost 以供应商返回值为最高可信来源；缺失时才使用版本化本地价格表估算。

## Fast-Fail 精确定义

“取消 fallback”指取消**静默且改变业务语义**的 fallback，不是删除所有合理默认值：

- 禁止：模型列表请求失败后伪装成候选模型成功返回。
- 禁止：协议解析失败后返回空正文、空数组或 `ok=true`。
- 禁止：工具/搜索/导入失败后只写日志或返回普通字符串，主流程仍视为成功。
- 禁止：供应商失败后自动切换另一供应商或模型。
- 允许：用户显式开启、UI 明确展示、事件中记录原因的 fallback；例如用户主动开启图片占位降级。
- 允许：纯展示默认值、向后兼容字段迁移；但不得隐藏数据损坏或上游失败。
- 允许：对幂等请求的有限重试；必须有重试次数、退避、最终错误和 requestId，不得无限重试。

## 当前基线（2026-07-10）

- LLM 主干：`backend/app/llm/openai_compat.py`，目前以 OpenAI Chat Completions 消息、工具与 SSE 格式为核心。
- 已发现静默样例：`list_models_openai_compat()` 捕获异常返回 `[]`；`GET /llm/models` 再回退候选模型/默认模型。
- 生成 SSE 错误目前主要为 `event:error {message}`，缺少统一 code/source/retryable/requestId。
- `ChatMessage` 已有 reasoning/tool/TTS 元数据，但没有 generation usage、TTFT、总耗时、缓存、cost。
- HTTP 出站日志已有 `durationMs`，但不是消息级计费账本，也没有统一 usage 归一化。
- 网络搜索已有 Tavily / 博查；部分失败以 JSON 字符串作为工具结果返回，尚未进入统一错误契约。
- 统计 UI 目标位置：`SettingsDrawerGlobalAppSection.vue` 的“应用与更新”accordion 内、成本计算器按钮上方。

## 当前实施进度（2026-07-10）

- T-801 已完成：统一错误 envelope、requestId、REST/SSE handler、上游错误映射、前端 typed error 与错误栈。
- T-802 前两批已完成：LLM/generate fast-fail，以及 Storage/chat/fork 损坏数据可见化、索引自愈、cleanup-only 日志。
- 当前门禁：后端 168 tests、前端 123 tests、前端 build 全通过。
- fork index 性能基线：1000 会话、99 fork 冷重建 `410.05 ms`，回归门槛 `< 5000 ms`。
- 已确认正文正则未在 generate 落库前调用，登记为 F-010 契约缺口，待唯一语义决策。
- 下一批：Assistant/tools 脏消息、工具参数与 REST/SSE 错误收口。

## 统一错误契约

REST 与 SSE 共用字段：

```json
{
  "code": "provider_auth_failed",
  "message": "Anthropic API Key 无效或无权限",
  "detail": "HTTP 401: invalid x-api-key",
  "source": "llm.anthropic",
  "retryable": false,
  "requestId": "req_xxx",
  "provider": "anthropic",
  "protocol": "anthropic_messages",
  "upstreamStatus": 401,
  "suggestedAction": "检查 API 预设中的 Key 与权限"
}
```

- REST：HTTP 状态码与错误类型一致，禁止业务失败返回 200。
- SSE：终止事件统一为 `event:error`，携带完整错误体与 `terminal:true`；失败流不得再发 `done`。
- 后台任务：状态持久化并通过现有通知/错误栈展示，不得只 `print` / `console.debug`。
- 工具调用：协议层保留结构化 tool error；模型可见文本与用户可见错误分开，避免模型重试掩盖真实失败。
- 每个入口生成 `requestId`；出站 HTTP、SSE、日志、usage ledger 使用同一关联 ID。

## 任务分解与顺序

| ID | 优先级 | 内容 | 依赖 | 完成定义 |
|----|--------|------|------|----------|
| T-801 | P0 | Fast-Fail 错误基座：错误类型、REST/SSE envelope、requestId、前端解析与错误栈 | 无 | 契约测试通过；不再只传裸字符串 |
| T-802 | P0 | 全 backend 静默 fallback 审计与迁移 | T-801 | backend/app 覆盖矩阵完成；每个 catch 有明确策略 |
| T-803 | P0 | 性能基线与基础设施：profiling、共享 HTTP client、超时/连接池、chatId/usage 索引、锁与原子写 | T-801 | 有基准、SLO、回归测试；优化有前后数据 |
| T-804 | P0 | LLM 协议内核：统一请求、消息、工具、流事件、usage、错误接口 | T-801 | OpenAI-compatible 先迁入且行为不变 |
| T-805 | P0 | 原生协议：OpenAI Responses、Anthropic Messages、Gemini generateContent/streamGenerateContent | T-804 | 三套原生非流/流/错误/usage 契约测试 |
| T-806 | P0 | 多套工具调用与消息维护；Anthropic 显式缓存开关 | T-805 | 工具 round-trip、消息转换、缓存开关端到端 |
| T-807 | P0 | 消息 generation metadata + append-only usage ledger | T-804 | 云端 usage/cost 原样保留并归一化；写入幂等 |
| T-808 | P1 | 定价引擎、会话/全局统计 API 与设置页仪表盘 | T-807 | 会话/全局/按模型汇总与成本来源可解释 |
| T-809 | P1 | 网络搜索供应商与 provider-native grounding 扩展 | T-801, T-804 | 无静默切换；每个 provider 独立契约测试 |
| T-810 | P1 | 生成、Assistant、MVU、知识图谱、正文正则、TTS 性能与健壮性 | T-801, T-803 | 分领域 benchmark + 异常注入测试 |
| T-811 | P1 | storage、import/export、integrity、fork/chat 索引与警告扩展 | T-801, T-803 | orphan、跳过项、锁冲突均可感知 |
| T-812 | P1 | `useChatGeneration`：前端 SSE 编排提炼与统一 error/meta/done 消费 | T-801, T-807 | ChatPage 只保留页面编排；停止/失败不丢消息 |
| T-813 | P1 | 数据迁移、隐私、安全与向后兼容 | T-807, T-808 | 旧 JSON 可加载；密钥/响应敏感字段不进账本 |
| T-814 | P0 | 全链路验证、文档与 v0.800 发布门禁 | 全部 | pytest、前端 test/build、性能门禁、错误审计通过 |

## 全后端覆盖矩阵

每个区域都必须完成“失败语义 + 性能 + 健壮性 + 测试”四列，不接受只改生成路由：

| 区域 | Fast-Fail 重点 | 性能/健壮性重点 |
|------|----------------|-----------------|
| `llm/`、`routes/llm.py` | 协议/鉴权/模型列表失败不得返回空成功 | client 复用、流解析、usage 捕获 |
| `routes/generate.py` | SSE terminal error、持久化失败、工具失败 | 去重复路径、首字延迟、流背压 |
| Assistant / tools | 工具错误不可吞；轮次上限可解释 | schema 缓存、批量读取、超时 |
| MVU / KG / regex | Agent/解析/正则超时结构化 | 避免重复加载、增量处理 |
| storage / chats / fork | 缺失、损坏、锁失败不可默认空 | chatId 索引、缓存、原子写 |
| import/export / integrity | 跳过项必须 warning/error | 流式 ZIP、批处理扫描 |
| TTS | 子进程/平台/缓存失败可定位 | 生命周期、复用、缓存索引 |
| web search | provider/auth/quota/timeout 明晰 | 统一 client、配额、结果限制 |
| HTTP log / update / avatar / clipboard | 后台失败不得只 debug | I/O 边界、大小限制、清理 |

## v0.800 范围边界

### 纳入

- 原生多厂商对话协议、工具与流式。
- Anthropic prompt caching 显式启用按钮。
- 消息级 generation metadata、usage ledger、成本统计。
- 会话/全局/按模型统计 UI。
- 网络搜索供应商与原生 grounding 扩展。
- SSE composable、数据完整性与导出 warnings。

### 不纳入

- 新增传统数据库依赖；仍使用 JSON/JSONL + 索引文件 + 文件锁。
- 任何“自动选择最便宜模型/自动换供应商”策略。
- 以估算 token 覆盖供应商返回 token。
- 对供应商协议字段进行无文档依据的猜测；实现前必须查官方文档并留 fixture。
- Playwright 全量 E2E（仍可留 v0.900+）。

## 首批 read_first

- `docs/tasks/T-801-v0800-fast-fail-foundation.md`
- `docs/tasks/T-802-v0800-backend-fallback-audit.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
- `backend/app/llm/openai_compat.py`
- `backend/app/routes/llm.py`
- `backend/app/routes/generate.py`
- `backend/app/services/http_log.py`
- `backend/app/storage.py`
- `frontend/src/api/http.ts`
- `frontend/src/composables/useErrorStack.ts`

## 验证总门禁

```powershell
cd backend
python -m pytest tests/ -q

cd ..\frontend
npm run test
npm run build
```

另需新增：

- 全 backend 静默 fallback 静态审计清单。
- 协议 fixture / golden tests（流式拆包、工具调用、usage、错误）。
- 故障注入（超时、断流、损坏 JSON、锁冲突、部分写入）。
- 性能基线与回归门槛（不得只报告“感觉更快”）。
