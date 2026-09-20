# T-806 v0.800 工具与 Anthropic 缓存

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: **6A/6B/6C 完成**
- area: backend `llm/` + 预设 UI + 各协议工具路径
- priority: P0
- theme: Anthropic 缓存三档；多协议工具 round-trip；Responses 内建 web_search
- depends_on: T-805（完成）

## 目标

在 T-805 无工具主路径之上，补齐工具调用与 Anthropic 显式 prompt caching。禁止不支持时静默降级。

## 批次

| 批次 | 主题 | 完成定义 | 状态 |
|------|------|----------|------|
| **6A** | Anthropic cache：`off` / `5m` / `1h` | 预设字段 + UI（仅 anthropic_messages）+ adapter 注入；默认 off | ✅ |
| **6B** | Anthropic / Gemini / Responses 工具 round-trip | tool_use↔tool_result 等；有能力才启用 | ✅ |
| **6C** | Responses 内建 web_search 分流（Gemini CachedContents 已并入 v0.810 T-821） | 与主聊天 webSearchEnabled 对齐；Responses 不走 Tavily 循环 | ✅ |

## 6B 产品约定

- 调用方契约不变：入口仍是 OpenAI 形 `tools` / `tool_calls` / `role=tool`
- 出口仍是 `ChatCompletionMessage.tool_calls` + `StreamChunk(finish, tool_calls)`
- Anthropic：`tool_use` / `tool_result`
- Gemini：`functionDeclarations` / `functionCall` / `functionResponse`
- Responses：function tools（`function_call` / `function_call_output`）；内建 `web_search` 见 6C
- 禁止有 tools 却静默忽略

## 6A 摘要

- `anthropicPromptCache` off|5m|1h；system 块 `cache_control`

## 验收

```powershell
cd backend
python -m pytest tests/ -q
```
