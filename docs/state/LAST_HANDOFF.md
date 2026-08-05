# Last Handoff

- last_task: `T-805-5A-protocol-wiring`
- status: completed（T-805 整体仍 in-progress）
- summary: 将调用方接到 `get_adapter`/`runtime`；预设与全局可持久化 `protocol`；设置页可选协议；未实现协议 fast-fail。
- code_changes:
  - `schemas`：`SettingsLLM.protocol` / `ApiPreset.protocol`
  - `llm/preset_resolve.py`、`llm/runtime.py`、`routes/llm.py`
  - generate / assistant / mvu / web_search 传 `protocol`；SSE meta 用解析结果
  - 前端：`llmProtocols.ts`、PresetsTab / GlobalConnection / test-models
  - 测试：preset_resolve / protocol kernel / error contract 补丁
- known_gap:
  - **5B–5D**：Anthropic / Gemini / Responses 适配器尚未实现（UI 可选但会失败）
  - 工具与 Anthropic cache 三档属 T-806
  - usage ledger 属 T-807
- verification:
  - `cd backend && python -m pytest tests/ -q` → **231 passed**
- version_note: `backend/app/version.py` 仍为 `v0.700`
- next_read:
  1. `docs/tasks/T-805-v0800-native-llm-protocols.md`
  2. Anthropic Messages API（无工具路径；cache 默认 off）
- next_implementation: **T-805-5B** `providers/anthropic_messages.py`（无工具 nonstream+stream）。不要并行启动 T-806/T-807 除非用户要求。
