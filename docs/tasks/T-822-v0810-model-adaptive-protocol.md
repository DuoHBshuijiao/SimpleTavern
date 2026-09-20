# T-822 v0.810 模型自适应协议与参数翻译

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: **done**
- area: `backend/app/llm/resolution.py`、`preset_resolve.py`、`schemas.py`、7 个调用点（generate×4 / assistant / mvu_daemon / st_mvu_import_agent）、`SettingsDrawerPresetsTab.vue`
- priority: P0
- depends_on: T-820-A1（目录）

## 目标

用户在预设里选「自动（按模型识别）」时，按模型 id 关键字选出合适协议并翻译推理深度 / 缓存 / 参数。与 v0.800「不做隐藏协议降级」的关系：`auto` 是**用户可见、可关闭**的模式；实际结果写入 SSE `meta.protocolResolution` 与预设编辑器预览；用户显式选定协议时永不改写。

## 规则

- 家族匹配：`claude*`→anthropic；`gemini*`→gemini；`gpt-*|o1|o3|o4*|codex*`→openai；`deepseek|kimi|moonshot|glm|qwen|minimax|hunyuan|doubao|seed|mimo|step|ernie|yi|spark`→cn_best_effort；其余 generic。
- 协议切换（仅 `auto`）：claude 且供应商声明 `anthropic_messages`（api.anthropic.com / OpenRouter / Kimi coding / MiniMax anthropic / Cloudflare `/anthropic` / Bedrock）→ Anthropic；gemini 且 host 为 `generativelanguage` / Vertex → Gemini（自动去 `/openai` 后缀）；gpt/o 系列且 host 为 api.openai.com / Azure → Responses；其他保持 compat。供应商未声明时不切换并给可读原因。
- 推理深度：`ReasoningEffort` 增加 `max`；`clamp_reasoning_effort(effort, family)` 用 models.json `reasoningEfforts` 向下取最近可用档（`max→xhigh→high…`；`none` 不可用时取最低档），产生 `adjustments: reasoning_effort_clamped{from,to}`。写法：Chat `reasoning_effort`；Responses `reasoning.effort`；Anthropic `output_config.effort`（`none`→`thinking.type=disabled`）；Gemini `thinkingConfig.thinkingLevel`（`xhigh|max→high`，`none→thinkingBudget 0` 或 `minimal`）；中国厂商 `thinking/enable_thinking`。
- 其他：`max_tokens` 按家族选 `max_completion_tokens`/`max_output_tokens`；`temperature:false` 家族丢弃 temperature/top_p 并记 adjustment；`promptCache` 翻译：compat→Anthropic（`24h→1h`、`in_memory→5m`，`cacheKey` 丢弃并说明）、compat→Responses（保留 key；retention 按家族转 `prompt_cache_options`）、→Gemini（`explicit` 转 cachedContents，`ttl` 转秒）。只有用户原本开启缓存才写入。

## 输出

```python
@dataclass(frozen=True)
class ProtocolResolution:
    requested: str        # 预设值（含 auto）
    effective: str        # 实际协议
    provider_id: str | None
    family: str
    adjustments: list[dict]   # {type, from, to, reason}
    reasons: list[str]
```

SSE `meta.protocolResolution` 与 `POST /api/llm/resolve-preview` 返回同一结构。

## 前端

- 协议下拉新增「自动（按模型识别）」；新预设默认 `auto`，旧预设不动。
- 预设编辑器「将使用：Anthropic Messages · 缓存 5 分钟显式 · 推理 xhigh（max 不可用已降级）」预览。
- 全局「思考模式」下拉增加 `max`，语义为「会话未覆盖时的默认深度」。

## 验收

```powershell
cd backend
python -m pytest tests/test_protocol_resolution.py tests/test_reasoning_clamp.py -q
```
