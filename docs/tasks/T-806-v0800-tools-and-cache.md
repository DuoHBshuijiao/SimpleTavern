# T-806 v0.800 工具与 Anthropic 缓存

- status: in-progress（**6A 完成**；下一批 6B）
- area: backend `llm/` + 预设 UI + 各协议工具路径
- priority: P0
- theme: Anthropic 缓存三档；多协议工具 round-trip；Responses/Gemini 高级能力
- depends_on: T-805（完成）

## 目标

在 T-805 无工具主路径之上，补齐工具调用与 Anthropic 显式 prompt caching。禁止不支持时静默降级。

## 批次

| 批次 | 主题 | 完成定义 | 状态 |
|------|------|----------|------|
| **6A** | Anthropic cache：`off` / `5m` / `1h` | 预设字段 + UI（仅 anthropic_messages）+ adapter 注入；默认 off | ✅ |
| **6B** | Anthropic / Gemini / Responses 工具 round-trip | tool_use↔tool_result 等；有能力才启用 | 待办 |
| **6C** | Responses 内建 web_search 分流 + Gemini CachedContents | 与主聊天 web_search 策略对齐 | 待办 |

## 6A 产品约定

- 字段：`ApiPreset.anthropicPromptCache` / 全局 `SettingsLLM.anthropicPromptCache`
- 枚举：`off`（默认）| `5m` | `1h`（兼容旧布尔：true→`5m`，false→`off`）
- 仅 `protocol=anthropic_messages` 时 UI 展示
- 首批仅缓存 **system（instructions）** 稳定块；动态世界书不打 cache_control
- 上游缓存配置错误 → 直接报错，不静默去掉 cache 重试

## 6A 落地摘要

- `normalize_anthropic_prompt_cache` / `attach_protocol_extra_body`
- `anthropic_messages._system_with_cache`：`5m`/`1h` → system 文本块 + `cache_control`
- 前端：`frontend/src/constants/anthropicPromptCache.ts` + 全局/预设下拉

## 验收

```powershell
cd backend
python -m pytest tests/ -q
```
