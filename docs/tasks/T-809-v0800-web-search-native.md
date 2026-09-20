# T-809 v0.800 独立搜索供应商与模型原生联网

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**
- area: `web_search` + generate 原生工具 + Anthropic/Gemini adapter
- priority: P1
- theme: 无静默切换供应商；独立搜索与模型原生联网分轨
- depends_on: T-801、T-804、T-806-6C（Responses 内建搜索已完成）

## 目标

扩展独立搜索 API（Brave），并为 Anthropic Messages / Gemini generateContent 接入官方原生联网。失败不得改走 Tavily/博查。

## 完成定义

- 独立搜索：`provider=brave`，GET `https://api.search.brave.com/res/v1/web/search`，头 `X-Subscription-Token`。429 → `web_search_quota`；401/403 独立报错。
- 原生协议集合：`openai_responses` / `anthropic_messages` / `gemini_generate_content`。这些协议启用搜索时不要求独立搜索 Key，也不走本地函数工具循环。
- Anthropic：`{type:web_search_20250305,name:web_search}`；跳过 `server_tool_use` / `web_search_tool_result`。
- Gemini：`{googleSearch:{}}`；跳过 google_search functionCall。
- UI 文案区分「独立搜索供应商」与「模型原生联网」。设置增加 Brave Token / count。
- 助手工具仍走独立搜索（Tavily/博查/Brave），不伪装为原生 grounding。

## 路径

- `backend/app/services/web_search.py`、`backend/app/routes/web_search.py`、`backend/app/routes/generate.py`
- `backend/app/llm/providers/anthropic_messages.py`、`gemini_generate_content.py`
- `frontend/src/components/settings-drawer/SettingsDrawerGlobalWebSearchSection.vue`
