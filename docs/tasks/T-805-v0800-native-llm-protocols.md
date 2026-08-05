# T-805 v0.800 原生 LLM 协议

- status: in-progress（**5A 完成**；下一棒 5B Anthropic）
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
| **5B** | Anthropic Messages 无工具 | nonstream+stream 契约；有工具 fast-fail；缓存默认 off | 下一批 |
| **5C** | Gemini generateContent 无工具 | 勿与 v1beta/openai 混淆 | 待办 |
| **5D** | OpenAI Responses 无工具 | Items + typed SSE | 待办 |

## 5A 完成记录

- `SettingsLLM.protocol` / `ApiPreset.protocol`（缺省 `openai_compatible_chat`；旧数据补写）
- `LlmPresetCredentials.protocol`；`llm/runtime.py` 经 `get_adapter` 调用
- generate / assistant / mvu / web_search / `llm` 路由接线；SSE meta 使用解析出的 protocol/provider
- 前端：预设与全局「LLM 协议」下拉；`test-models` 传 protocol
- 未注册协议（Anthropic/Gemini/Responses）选择后 fast-fail，不静默回退
- 门禁：`cd backend && python -m pytest tests/ -q` → **232 passed**

### 5A 审查修复

- 前端未知协议不再静默改写为 compat；下拉可展示未知项
- `st_mvu_import_agent`、TTS `/preprocess` 改走 `resolve` + `runtime` + `protocol`
- `provider_id_for_protocol` 对未知协议返回 `unknown`

## T-806 边界

- Anthropic 缓存三档：`off` / `5m` / `1h`
- 工具 round-trip；Responses 内建 web_search 分流；Gemini CachedContents
- 落库工具形状改造

## 流式说明

usage 仅终态可信，可接受；不阻塞本任务。各 adapter 仍须在终态调用 `decode_usage` 供日后 T-807。

## 验收

```powershell
cd backend
python -m pytest tests/ -q
```
