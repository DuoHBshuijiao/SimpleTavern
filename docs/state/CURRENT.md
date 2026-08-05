# 当前任务

- current: `v0.800 / T-805`
- status: in-progress（**5A✅ 5B✅ 5C✅**；下一棒 **5D OpenAI Responses**）
- next_read: `docs/tasks/T-805-v0800-native-llm-protocols.md`
- goal: 建立后端可信执行层——全 backend fast-fail、取消静默 fallback、用户可感知错误、性能与健壮性、原生多厂商协议、精确 usage/cost

## 版本宣告

- T-801–T-804、T-805-5A/5B/5C 已完成。`backend/app/version.py` 暂保持 `v0.700`。

## v0.800 第一阶段

1. T-801–T-804：✅
5. T-805：原生协议。← **5A–5C 完成，进行 5D**

## T-805-5C 摘要

- Gemini 原生 generateContent/streamGenerateContent；拒绝 `/v1beta/openai` 兼容端点。

## 必读

- `docs/tasks/T-805-v0800-native-llm-protocols.md`
- OpenAI Responses API（Items + typed SSE）
