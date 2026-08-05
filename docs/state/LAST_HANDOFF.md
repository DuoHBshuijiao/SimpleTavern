# Last Handoff

- last_task: `T-804-llm-protocol-kernel`
- status: completed
- summary: 建立 LLM ProviderAdapter 内核；OpenAI-compatible Chat Completions 迁入适配器；`openai_compat` 保留稳定 ABI。
- code_changes:
  - 新增 `llm/types.py`、`protocol.py`、`registry.py`、`providers/openai_compatible_chat.py`。
  - `openai_compat.py` 改为再导出门面。
  - 测试：`test_llm_protocol_kernel.py`；openai_compat mock 路径更新。
- known_gap:
  - 调用方尚未经 registry 选协议（4C）；原生 Responses/Anthropic/Gemini 属 T-805。
  - usage ledger / generation metadata 属 T-807。
- verification:
  - `cd backend && python -m pytest tests/ -q` → 226 passed。
- version_note: `backend/app/version.py` 仍为 `v0.700`。
- next_read:
  1. `docs/tasks/T-804-v0800-llm-protocol-kernel.md`
  2. `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md` §3
  3. 新建 `docs/tasks/T-805-*.md`（若无）
- next_implementation: T-805 原生协议（Responses / Anthropic / Gemini）。不要并行启动 T-807 除非用户要求。
