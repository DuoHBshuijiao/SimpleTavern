# Last Handoff

- last_task: `T-806-6B-protocol-tools`
- status: completed（6B；T-806 整体仍进行中）
- summary: Anthropic / Gemini / OpenAI Responses 三协议 function tools round-trip；调用方仍用 OpenAI 形 tools/tool_calls。
- code_changes:
  - `anthropic_messages.py`：tools → Anthropic tools；tool_use/tool_result 消息往返；流式 finish.tool_calls
  - `gemini_generate_content.py`：functionDeclarations / functionCall / functionResponse
  - `openai_responses.py`：function_call / function_call_output；内建 web_search 仍拒绝
  - 前端协议下拉去掉「无工具」标注
  - 对应单测更新
- known_gap:
  - Responses 内建 web_search、Gemini CachedContents → **T-806-6C**
  - usage ledger → **T-807**
- verification:
  - `cd backend && python -m pytest tests/ -q` → **280 passed**
- version_note: `backend/app/version.py` 仍为 `v0.700`
- next_read:
  1. `docs/tasks/T-806-v0800-tools-and-cache.md`（6C）
  2. 设计规格 §9 原生联网
- next_implementation: **T-806-6C**（Responses 内建 web_search 分流 + Gemini CachedContents）。不要并行启动 T-807 除非用户要求。
