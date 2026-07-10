# 当前任务

- current: `v0.800`
- status: in-progress（规划完成，代码尚未开始）
- next_read: `docs/tasks/T-801-v0800-fast-fail-foundation.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- v0.700 前端范围已关闭。
- 当前正式进入 v0.800 规划与实施阶段。
- 本轮只更新文档，未修改代码；`backend/app/version.py` 暂保持 `v0.700`，待首批实现与门禁通过后再改。

## v0.800 第一阶段

1. T-801：统一错误基座（REST/SSE/requestId/前端错误栈）。
2. T-802：全 backend 静默 fallback 审计与迁移。
3. T-803：性能基线、profiling、共享 HTTP client、索引与 I/O。
4. T-804：LLM 协议内核；随后接原生 OpenAI Responses / Anthropic / Gemini。

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
