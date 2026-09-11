# T-832 v0.820 Bedrock / Mistral / Vertex 原生协议（P1，可滑动）

- status: **later**
- area: `backend/app/llm/providers/`
- priority: P1
- depends_on: T-820-A2（Bedrock Anthropic invoke 变体已有；eventstream 仍 fast-fail）

## 目标

- AWS Bedrock Converse + 原生 `invoke-with-response-stream` eventstream 解析。
- Mistral Conversations API。
- Vertex Anthropic `rawPredict`。

当前流式遇 Bedrock eventstream 仍返回 `provider_capability_unsupported`（关流式可用 invoke）。本版 P0 不阻塞 T-830/T-831。
