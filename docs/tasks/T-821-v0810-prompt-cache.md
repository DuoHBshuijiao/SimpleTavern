# T-821 v0.810 分协议显式缓存策略 + 教学弹窗

- status: **done**
- area: `backend/app/llm/params.py`、`llm/prompt_cache.py`、四个 adapter、`schemas.py`、`SettingsDrawerPresetsTab.vue`、`components/prompt-cache/`
- priority: P0
- depends_on: T-820-A1（目录：模型家族门槛）、T-822（协议解析与翻译）

## 事实清单（官方文档，实施前勿再猜字段）

- **OpenAI**（[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching#summary-of-model-differences)）：GPT-5.6+ Responses 用 `prompt_cache_options: {mode: implicit|explicit, ttl: "30m"}` + 内容块 `prompt_cache_breakpoint: {mode: "explicit"}`（≤4 写 / 50 读；顶层 `instructions` 不能打断点，需放 developer message 的 `input_text` 块）；写入 1.25×、读 0.1×、最小 1024 token。GPT-5.5 及更早用 `prompt_cache_retention: in_memory|24h`。`prompt_cache_key` 全模型通用。Chat Completions 仅 `prompt_cache_key/prompt_cache_retention`，无断点。
- **Anthropic**：`cache_control: {type: ephemeral, ttl?: "5m"|"1h"}`；顶层 `cache_control` = 自动缓存（断点自动落到最后可缓存块），与块级断点共占 4 槽；1h 必须排在 5m 前；最小可缓存 512/1024/2048/4096 按模型；用量 `cache_read_input_tokens/cache_creation_input_tokens`（+ `cache_creation.ephemeral_5m_input_tokens/ephemeral_1h_input_tokens`）。
- **Gemini**：隐式缓存默认开启（2.5+，最小 2048/4096）；显式 `cachedContents.create`（`contents`+`systemInstruction`+`tools`、`ttl` 秒，默认 1h）→ `generateContent` 传 `cachedContent`；用量 `usageMetadata.cachedContentTokenCount`。
- **中国厂商**：DeepSeek（`prompt_cache_hit_tokens/prompt_cache_miss_tokens`）/Kimi/GLM/MiniMax/混元 自动前缀缓存无参数；阿里百炼/Qwen 显式缓存为消息 content 数组内 `cache_control: {type: ephemeral}`（固定 5 分钟、≤4 标记、≥1024 token）。

## 数据模型

```ts
interface PromptCacheConfig {
  mode: 'auto' | 'off' | 'implicit' | 'explicit' | 'best_effort'
  ttl?: '5m' | '1h' | '30m' | 'in_memory' | '24h' | number   // number = 秒（Gemini）
  breakpoints?: ('system' | 'tools' | 'history_tail')[]
  cacheKey?: 'per_chat' | 'per_character' | 'global' | string
  explicitMarkers?: boolean   // 百炼/Qwen 消息级 cache_control
}
```

迁移：`anthropicPromptCache: off` → `{mode:'off'}`；`5m/1h` → `{mode:'explicit', ttl}`；旧字段保留读兼容，写入时同步回填。

## 批次

| 批次 | 完成定义 | 状态 |
|------|----------|------|
| **B1** | `promptCache` 字段 + 迁移；`params.py` 统一参数注册表；Anthropic 顶层/块级/tools 断点 + TTL 排序；Responses `prompt_cache_key/options/breakpoint` 或 `retention`；Chat `key/retention` 仅 OpenAI/Azure；百炼 `cache_control`；Gemini cachedContents（`data/llm_cache_index.json`，404 重建一次并 warn）；Usage 五源归一化；Chat 流式 usage 帧（`stream_options.include_usage`）；SSE `meta.cache` + `done.usage` | ✅ |
| **B2** | 预设编辑器 + 全局连接区「缓存策略」区块（模式 / 保留时长 / 断点位置 / 分组键，按协议+家族过滤；无效组合禁选并给原因）；消息 usage 徽标显示缓存读/写 | ✅ |
| **B3** | `PromptCacheGuideModal.vue` 近全屏（`max-w-5xl h-[92vh]`）7 步：前缀与 KV → 断点位置 → 写/读成本计算器 → 保留时长沙漏 → 厂商差异卡 → 逐步完成本预设并预览请求体片段 → 可选探测（默认不勾）；reduced-motion 静态分帧；Esc/焦点恢复 | ✅ |

## 验收

```powershell
cd backend
python -m pytest tests/test_prompt_cache_params.py tests/test_gemini_cached_contents.py -q
cd ../frontend
npm run test -- PromptCache
```

手动：真实 key 对 Responses（GPT-5.6+）、Anthropic、Gemini、百炼各发两次，确认 `done.usage` 出现 cache write → read。
