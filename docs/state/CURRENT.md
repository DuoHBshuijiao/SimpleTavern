# 当前任务

- current: `v0.800 / T-805`
- status: in-progress（**5A✅ 5B✅**；下一棒 **5C Gemini generateContent**）
- next_read: `docs/tasks/T-805-v0800-native-llm-protocols.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- v0.700 前端范围已关闭。
- 当前正式进入 v0.800 实施阶段。
- T-801–T-804、T-805-5A/5B 已完成。`backend/app/version.py` 暂保持 `v0.700`。

## v0.800 第一阶段

1. T-801：统一错误基座。✅
2. T-802：静默 fallback 审计与迁移。✅
3. T-803：性能基础设施。✅
4. T-804：LLM 协议内核。✅
5. T-805：原生协议。← **5A/5B 完成，进行 5C**

## T-805-5B 摘要

- Anthropic Messages 无工具适配器已注册；工具/缓存仍归 T-806。

## 必读

- `docs/01-ROADMAP.md`
- `docs/tasks/T-805-v0800-native-llm-protocols.md`
- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
