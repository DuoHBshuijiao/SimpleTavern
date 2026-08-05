# T-805 v0.800 原生 LLM 协议

- status: in-progress（**5A✅ 5B✅ 5C✅**；下一棒 5D OpenAI Responses）
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
| **5C** | Gemini generateContent 无工具 | 勿与 v1beta/openai 混淆 | ✅ |
| **5D** | OpenAI Responses 无工具 | Items + typed SSE | 下一批 |

## 5C 完成记录

- 新增 `providers/gemini_generate_content.py`：原生 `generateContent` / `streamGenerateContent?alt=sse`
- Auth：`x-goog-api-key`；assistant→`model`；system→`systemInstruction`
- 拒绝 Base URL 含 `/openai`（避免与兼容层混淆）
- 工具 / functionCall → fast-fail；`thought: true` → reasoning；usageMetadata → decode_usage
- 门禁：**253 passed**（见下方验收）

## 5B / 5A

- Anthropic Messages 无工具；协议字段 + runtime 接线（含审查修复）

## T-806 边界

- Anthropic 缓存三档：`off` / `5m` / `1h`
- 工具 round-trip；Responses 内建 web_search 分流；Gemini CachedContents
- 落库工具形状改造

## 验收

```powershell
cd backend
python -m pytest tests/ -q
```
