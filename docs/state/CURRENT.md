# 当前任务

- current: `v0.800 / T-806`
- status: ready（T-805 5A–5D 全部完成）
- next_read: `docs/01-ROADMAP.md`（T-806）与设计规格工具/缓存章节
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- T-801–T-805 已完成。`backend/app/version.py` 暂保持 `v0.700`，待 v0.800 发布门禁完成后再改。

## v0.800 第一阶段

1. T-801–T-804：✅
5. T-805：原生协议（compat / Anthropic / Gemini / Responses 无工具）。✅
6. T-806：工具 round-trip + Anthropic cache 三档 + Responses/Gemini 高级能力。← 下一批

## T-805 摘要

- 四协议已注册；主路径无工具；工具/缓存明确推迟到 T-806。

## 必读

- `docs/01-ROADMAP.md`
- `docs/tasks/T-805-v0800-native-llm-protocols.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
