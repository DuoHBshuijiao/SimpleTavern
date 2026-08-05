# 当前任务

- current: `v0.800 / T-806-6C`
- status: ready（6A/6B 完成；下一批 6C）
- next_read: `docs/tasks/T-806-v0800-tools-and-cache.md`（6C）
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- T-801–T-805 完成；T-806-6A/6B 完成。`backend/app/version.py` 暂保持 `v0.700`，待 v0.800 发布门禁完成后再改。

## v0.800 第一阶段

1. T-801–T-804：✅
5. T-805：原生协议（compat / Anthropic / Gemini / Responses 无工具）。✅
6. T-806：工具 round-trip + Anthropic cache 三档 + Responses/Gemini 高级能力。
   - **6A** Anthropic cache `off|5m|1h`：✅
   - **6B** 工具 round-trip：✅
   - **6C** Responses web_search / Gemini CachedContents：← 下一批

## T-806-6B 摘要

- Anthropic / Gemini / Responses 均支持 OpenAI 形 function tools round-trip（assistant/mvu/web_search 无需改解析形状）。
- Responses 内建 web_search 仍明确 fast-fail（归 6C）。

## 必读

- `docs/01-ROADMAP.md`
- `docs/tasks/T-806-v0800-tools-and-cache.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
