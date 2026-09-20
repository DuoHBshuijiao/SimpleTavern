# T-820 v0.810 供应商目录扩充与特殊鉴权支持

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: **done**（A3 OAuth 滑到 v0.820）
- area: `backend/app/llm/catalog/`、`backend/scripts/sync_llm_catalog.py`、`frontend/src/constants/llmProviderPresets.ts`、`LlmPresetNameCombobox.vue`、adapters
- priority: P0
- depends_on: T-805（完成）、T-806-6A/6B（完成）

## 目标

以 [pi `packages/ai/src/providers`](https://github.com/earendil-works/pi/tree/main/packages/ai/src/providers) 为**唯一信源**扩充内建供应商目录；模型元数据取 models.dev `api.json` 与 OpenRouter `/api/v1/models` 快照。现有 16 条 `LLM_PROVIDER_PRESETS`（OpenRouter/硅基流动/DeepSeek/月之暗面/MiniMax/AI Studio/OpenAI/xAI/Mistral/Perplexity/Fireworks/混元/百炼/智谱/Azure/Bedrock）经核查保留并映射到新目录 id。Zenmux 等第三方经调查确认数据安全受监管、调用记录 id 与元数据可追溯，可保留。

## 批次

| 批次 | 主题 | 完成定义 | 状态 |
|------|------|----------|------|
| **A1** | 目录数据 + UI | 脚本产出两份 generated JSON；`catalog.py` 按 host / 模型 id 匹配；`GET /api/llm/catalog`；combobox 分组（国内 / 海外 / 网关与聚合 / 需登录）+ 搜索 + 协议/缓存徽标；选择联动 `baseUrl/protocol/authStyle/providerParams`，占位符表单替代 `requiresManualEdit` 提示；旧预设 baseUrl 仍能匹配 | ✅ |
| **A2** | AuthStyle / URL 模板 | `bearer`（默认）/`x-api-key`/`api-key`+`?api-version=`（Azure）/`x-goog-api-key`（Gemini/Vertex Express）/`query_key`；Anthropic Bedrock 变体（`anthropic_version: bedrock-2023-05-31`、URL 含 `{region}/{model}`、去 `model`）；Cloudflare AI Gateway / Workers AI / Vercel AI Gateway / OpenCode / HuggingFace router / Groq / Cerebras / Baseten / Together / NVIDIA / Ant Ling / Xiaomi / Qwen token plan / Z.AI coding / Kimi coding / MiniMax anthropic 条目 | ✅ |
| **A3** | OAuth 厂商 | GitHub Copilot 设备码 / OpenAI Codex PKCE。**已滑到 v0.820** | ➡ v0.820 |

## 数据模型

`LlmProviderCatalogEntry`：`id, label, name, region: cn|global, group: cn|global|gateway|oauth, baseUrlTemplate, placeholders[]{key,label,hint,example}, authStyle, defaultProtocol, supportedProtocols[], cacheStrategy: explicit|implicit|best_effort|none, docsUrl, keywords[], requiresOAuth, legacyIds[]`。

`ApiPreset` 新字段（前后端同步，`extra="allow"` 兼容旧数据）：`providerId?`、`providerParams?: Record<string,string>`（region / resource / account_id / gateway_id / location / project / api_version）、`authStyle?`。

## 不做

- Bedrock Converse 原生协议、Mistral Conversations API、Vertex Anthropic `rawPredict`（记 v0.820）。

## 验收

```powershell
cd backend
python scripts/sync_llm_catalog.py --check   # 产物与源一致
python -m pytest tests/test_llm_catalog.py tests/test_auth_styles.py -q
cd ../frontend
npm run test -- llmProviderPresets LlmPresetNameCombobox
```
