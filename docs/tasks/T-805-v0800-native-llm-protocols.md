# T-805 v0.800 原生 LLM 协议

- status: in-progress（**5A✅ 5B✅**；下一棒 5C Gemini）
- area: backend `llm/` + 预设/设置 UI
- priority: P0
- theme: 协议选择与 registry 接线；原生 Anthropic / Gemini / Responses 分批落地；工具与缓存归 T-806
- depends_on: T-804（完成）

## 目标

在 T-804 ProviderAdapter 之上接入协议选择，并分批实现原生协议的无工具主路径。禁止失败时静默退回 `openai_compatible_chat`。

## 批次

| 批次 | 主题 | 完成定义 | 状态 |
|------|------|----------|------|
| **5A** | `ApiPreset.protocol` + preset_resolve + `get_adapter` 接线 + 设置页/test-models | 默认 compat 行为不变；未知/未实现 protocol fast-fail | ✅ |
| **5B** | Anthropic Messages 无工具 | nonstream+stream 契约；有工具 fast-fail；缓存默认 off | ✅ |
| **5C** | Gemini generateContent 无工具 | 勿与 v1beta/openai 混淆 | 下一批 |
| **5D** | OpenAI Responses 无工具 | Items + typed SSE | 待办 |

## 5B 完成记录

- 新增 `providers/anthropic_messages.py`：OpenAI 形 messages → Anthropic Messages
- 支持 nonstream / stream（`text_delta`→content，`thinking_delta`→reasoning）
- `tools` / `tool` 角色 / `tool_use` / `input_json_delta` → `provider_capability_unsupported`
- 不发送 `cache_control`（缓存三档归 T-806）
- `max_tokens` 缺省 4096；thinking 开启时 temperature=1 并映射 budget
- registry 已注册；前端标签改为「Anthropic Messages（无工具）」
- 门禁：`cd backend && python -m pytest tests/ -q` → **243 passed**

## 5A 完成记录

- `SettingsLLM.protocol` / `ApiPreset.protocol`；`llm/runtime.py`；调用方接线
- 审查修复：未知协议不静默改写；ST MVU / TTS preprocess 走 runtime

## T-806 边界

- Anthropic 缓存三档：`off` / `5m` / `1h`
- 工具 round-trip；Responses 内建 web_search 分流；Gemini CachedContents
- 落库工具形状改造

## 流式说明

usage 仅终态可信；adapter 在终态调用 `decode_usage` 供日后 T-807。

## 验收

```powershell
cd backend
python -m pytest tests/ -q
```
