# Last Handoff

- last_task: `T-805-5A-protocol-wiring` + bugfix
- status: completed（T-805 整体仍 in-progress）
- summary: 5A 接线完成；已修复审查发现的协议静默改写/旁路调用问题。
- code_changes:
  - 5A：protocol 字段、runtime、调用方接线、设置页下拉
  - 修复：前端 `normalizeLlmProtocol` 仅空值回落；未知协议保留并在下拉展示
  - 修复：`st_mvu_import_agent` / TTS preprocess 改走 `resolve` + `runtime` + `protocol`
  - 修复：未知协议 `provider_id_for_protocol` → `unknown`
- known_gap:
  - **5B–5D**：Anthropic / Gemini / Responses 适配器尚未实现
  - 工具与 Anthropic cache 三档属 T-806
  - usage ledger 属 T-807
- verification:
  - `cd backend && python -m pytest tests/ -q` → **232 passed**
- version_note: `backend/app/version.py` 仍为 `v0.700`
- next_read:
  1. `docs/tasks/T-805-v0800-native-llm-protocols.md`
  2. Anthropic Messages API（无工具路径；cache 默认 off）
- next_implementation: **T-805-5B** `providers/anthropic_messages.py`（无工具 nonstream+stream）。
