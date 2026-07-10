# 当前任务

- current: `v0.800 / T-802`
- status: in-progress（T-801 已完成，T-802 首批 LLM/generate 已完成）
- next_read: `docs/tasks/T-802-v0800-backend-fallback-audit.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- v0.700 前端范围已关闭。
- 当前正式进入 v0.800 实施阶段。
- T-801 已完成错误基座与最小示范迁移；`backend/app/version.py` 暂保持 `v0.700`，待 v0.800 发布门禁完成后再改。

## T-801 已完成

- 后端：统一 AppError/ErrorEnvelope、全局异常处理、requestId、SSE meta/error/done 与上游错误映射。
- 示范路径：`/llm/test-models`、`/generate/stream`、网络搜索未配置 fast-fail。
- 前端：typed REST/SSE `ApiError`、旧错误兼容、错误栈建议操作/requestId 展示。
- 日志：出站记录关联 requestId，Authorization/API Key/cookie 脱敏。
- 门禁：后端 129 tests、前端 121 tests、前端 build 全通过。

## v0.800 第一阶段

1. T-801：统一错误基座（REST/SSE/requestId/前端错误栈）。✅
2. T-802：全 backend 静默 fallback 审计与迁移。← 首批完成，下一批 Storage/chat/fork
3. T-803：性能基线、profiling、共享 HTTP client、索引与 I/O。
4. T-804：LLM 协议内核；随后接原生 OpenAI Responses / Anthropic / Gemini。

## T-802 首批已完成

- 机器可读清单：`docs/audits/v0800-backend-fallback-inventory.md`。
- LLM：模型列表空结果、非流空响应、非法 SSE、空流和断流全部 fast-fail。
- Generate：draft/group/interject 对齐 requestId、REST/SSE envelope；group/interject 搜索未配置不再静默关闭。
- Tools：网络搜索工具坏参数不再退 `{}` 执行。
- 守卫：已迁域 broad except/裸 SSE/旧 JSON 错误静态回归测试。
- 已知契约缺口：正文正则目前未在 generate 落库前调用，F-010 待产品语义确认。
- 门禁：后端 150 tests、前端 121 tests、前端 build 全通过。

## v0.800 核心交付

- 无静默 fallback；显式 fallback 必须用户启用并可见。
- 原生多厂商协议、多套工具调用/消息维护/流式方式。
- Anthropic prompt caching 显式开关。
- 消息 generation metadata：token、cache、TTFT、总耗时、cost。
- usage ledger 与会话/全局/按模型成本统计。
- SettingsDrawer “应用与更新”内、成本计算器上方的统计 UI。
- 搜索供应商与模型原生联网能力扩展。
- 所有 backend 组件的性能/健壮性覆盖矩阵。

## 必读

- `docs/tasks/T-800-v0800-backend-performance.md`
- `docs/tasks/T-801-v0800-fast-fail-foundation.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
