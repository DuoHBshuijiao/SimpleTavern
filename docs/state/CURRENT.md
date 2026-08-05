# 当前任务

- current: `v0.800 / T-805`
- status: in-progress（**5A 完成**；下一棒 **5B Anthropic Messages**）
- next_read: `docs/tasks/T-805-v0800-native-llm-protocols.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- v0.700 前端范围已关闭。
- 当前正式进入 v0.800 实施阶段。
- T-801–T-804 已完成；T-805-5A 已完成。`backend/app/version.py` 暂保持 `v0.700`，待 v0.800 发布门禁完成后再改。

## v0.800 第一阶段

1. T-801：统一错误基座。✅
2. T-802：静默 fallback 审计与迁移。✅
3. T-803：性能基础设施。✅
4. T-804：LLM 协议内核（OpenAI-compatible 迁入）。✅
5. T-805：原生协议 OpenAI Responses / Anthropic / Gemini。← **5A 完成，进行 5B**

## T-805-5A 摘要

- 预设/全局 `protocol` + `runtime` + 调用方接线；设置页协议下拉。
- 未实现协议 fast-fail；默认仍为 OpenAI Compatible Chat。

## v0.800 核心交付

- 无静默 fallback；显式 fallback 必须用户启用并可见。
- 原生多厂商协议、多套工具调用/消息维护/流式方式。
- Anthropic prompt caching 显式开关（产品枚举 `off`/`5m`/`1h`，归 T-806）。
- 消息 generation metadata：token、cache、TTFT、总耗时、cost。
- usage ledger 与会话/全局/按模型成本统计。
- SettingsDrawer “应用与更新”内、成本计算器上方的统计 UI。
- 搜索供应商与模型原生联网能力扩展。
- 所有 backend 组件的性能/健壮性覆盖矩阵。

## 必读

- `docs/01-ROADMAP.md`
- `docs/tasks/T-805-v0800-native-llm-protocols.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
