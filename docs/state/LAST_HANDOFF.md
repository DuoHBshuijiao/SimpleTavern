# Last Handoff

- last_task: `T-802-batch-1-llm-generate`
- status: completed（T-802 overall in-progress）
- summary: 建立全 backend fallback 首轮 P0/P1 清单，并完成 LLM/model-list/generate 首批静默失败迁移。
- code_changes:
  - 新增 `docs/audits/v0800-backend-fallback-inventory.md`，覆盖八个 backend 领域高风险项。
  - `/llm/models`、`/llm/test-models` 空列表统一 `model_list_empty`，不回退本地候选、不返回 200 + `[]`。
  - OpenAI-compatible 空响应、非法 SSE、空流、无结束标记分别 fast-fail。
  - 搜索工具非法参数/未知工具统一 `tool_call_invalid`，不再退 `{}` 调用。
  - draft/group/interject 统一 requestId、SSE meta/terminal error/success-only done 和非流 ErrorEnvelope。
  - group/interject 搜索未配置在生成前 fast-fail。
  - 新增已迁域静态 silent-fallback 守卫。
- review_fixes:
  - 补 `/llm/test-models` 上游空列表 fast-fail。
  - 补工具运行时“坏参数不得调用 search”测试。
  - 补 group/interject 非流 envelope、空流、reasoning/tool-only 与无 `[DONE]` 正常结束测试。
  - 保持 OpenAI Chat Completions 严格字段：tool arguments 为 JSON string、tool index 为 integer、SSE 只接受 data/comment。
- known_gap:
  - generate 落库前未调用 `apply_content_regex_pipeline`，与工作区文档契约不一致；已登记 F-010，本批未改变持久化语义。
- verification:
  - T-802 focused contracts → 38 passed。
  - `cd backend && python -m pytest tests/ -q` → 150 passed。
  - `cd frontend && npm run test` → 121 passed。
  - `cd frontend && npm run build` → passed。
- version_note: `backend/app/version.py` 仍为 `v0.700`；待 v0.800 发布门禁完成后再改。
- next_read:
  1. `docs/tasks/T-802-v0800-backend-fallback-audit.md`
  2. `docs/audits/v0800-backend-fallback-inventory.md`
  3. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-802 第二批迁移 Storage/chat list/fork 损坏项；先决定 F-010 正文正则唯一契约，再进入相关修复。不要同时开始 T-804 协议内核或计量大改。
