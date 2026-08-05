# 当前任务

- current: `v0.800 / T-806-6A`
- status: in-progress（6A Anthropic cache 三档已落地，待用户提交；下一批 6B 工具）
- next_read: `docs/tasks/T-806-v0800-tools-and-cache.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- T-801–T-805 已完成；T-806-6A 完成。`backend/app/version.py` 暂保持 `v0.700`，待 v0.800 发布门禁完成后再改。

## v0.800 第一阶段

1. T-801–T-804：✅
5. T-805：原生协议（compat / Anthropic / Gemini / Responses 无工具）。✅
6. T-806：工具 round-trip + Anthropic cache 三档 + Responses/Gemini 高级能力。
   - **6A** Anthropic cache `off|5m|1h`：✅
   - **6B** 工具 round-trip：← 下一批
   - **6C** Responses web_search / Gemini CachedContents：待办

## T-806-6A 摘要

- 预设/全局字段 `anthropicPromptCache`；仅 `anthropic_messages` UI 展示。
- adapter 在 system 块注入 `cache_control`（ephemeral + ttl）；默认 off；上游错误不静默重试。

## 必读

- `docs/01-ROADMAP.md`
- `docs/tasks/T-806-v0800-tools-and-cache.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
