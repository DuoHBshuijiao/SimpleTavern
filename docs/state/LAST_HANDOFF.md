# Last Handoff

- last_task: `v0.800-planning-kickoff`
- status: completed（规划文档）；v0.800 implementation not started
- summary: 正式宣布进入 v0.800；范围升级为全 backend fast-fail/无静默 fallback、性能与健壮性、原生 OpenAI Responses/Anthropic/Gemini、多套工具/消息/流、Anthropic 缓存、消息 usage/cost/latency 元数据、usage ledger、会话/全局/按模型统计、搜索供应商扩展。
- code_changes: none（仅文档）
- version_note: `backend/app/version.py` 仍为 `v0.700`，不得在无实现/无门禁时提前改版本常量。
- baseline_evidence:
  - LLM 当前以 `backend/app/llm/openai_compat.py` 为单一主干。
  - `list_models_openai_compat` 与 `/llm/models` 存在失败→空列表→候选/默认模型静默回退，是 T-801/T-802 首个示范点。
  - ChatMessage 尚无 generation usage/cost 元数据；HTTP log 只有 durationMs。
  - 搜索当前为 Tavily/博查。
  - 成本统计 UI 目标为 `SettingsDrawerGlobalAppSection.vue`，成本计算器按钮上方。
- next_read:
  1. `docs/tasks/T-801-v0800-fast-fail-foundation.md`
  2. `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- first_implementation: 只做 T-801 错误基座与最小示范迁移；不要同时开始协议/计量大改。
- verify_when_implementing: backend pytest；frontend test/build；新增 REST/SSE error contract tests。
