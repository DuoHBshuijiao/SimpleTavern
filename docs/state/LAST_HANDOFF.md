# Last Handoff

- last_task: `T-806-6A-anthropic-prompt-cache`
- status: completed（6A；T-806 整体仍进行中）
- summary: Anthropic prompt cache 三档 `off|5m|1h`：schema/凭证/adapter system 块注入 + 设置 UI（仅 anthropic_messages）。
- code_changes:
  - `SettingsLLM` / `ApiPreset.anthropicPromptCache`（布尔 legacy → 5m/off）
  - `LlmPresetCredentials.anthropic_prompt_cache` + `attach_protocol_extra_body`
  - `anthropic_messages`：system 块 `cache_control`；去掉顶层静默 strip-only 策略
  - generate / assistant / mvu / TTS preprocess 接线
  - 前端：全局连接 + API 预设下拉（仅 Anthropic 协议可见）
  - 测试：`test_anthropic_messages` / `test_anthropic_prompt_cache` / `test_preset_resolve`
- known_gap:
  - 工具 round-trip（Anthropic/Gemini/Responses）→ **T-806-6B**
  - Responses 内建 web_search、Gemini CachedContents → **T-806-6C**
  - usage ledger → **T-807**
- verification:
  - `cd backend && python -m pytest tests/ -q` → **270 passed**
- version_note: `backend/app/version.py` 仍为 `v0.700`
- next_read:
  1. `docs/tasks/T-806-v0800-tools-and-cache.md`（6B）
  2. 设计规格工具章节
- next_implementation: **T-806-6B**（多协议工具 round-trip）。不要并行启动 T-807 除非用户要求。
