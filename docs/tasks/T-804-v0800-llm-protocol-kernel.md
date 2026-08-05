# T-804 v0.800 LLM 协议内核

- status: completed（4A/4B；4C 可选未做——调用方仍经 `openai_compat` ABI）
- area: backend `llm/`
- priority: P0
- theme: 统一 ProviderAdapter / 请求与流事件接口；现有 OpenAI-compatible 先迁入且行为不变
- depends_on: T-801（完成）、T-802（完成）、T-803（完成）

## 目标

建立可扩展的 LLM 协议内核，使后续原生协议（T-805）与工具/缓存（T-806）、usage（T-807）有稳定挂载点。本任务**不**实现 Responses / Anthropic / Gemini，也**不**落 usage ledger。

## read_first

- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md` §3
- `docs/tasks/T-800-v0800-backend-performance.md`
- `backend/app/llm/openai_compat.py`
- `backend/app/llm/preset_resolve.py`
- `backend/tests/test_openai_compat.py`

## 批次计划

| 批次 | 主题 | 落点 | 完成定义 |
|------|------|------|----------|
| **4A** | 内核类型 + Adapter Protocol + registry | `llm/types.py`、`protocol.py`、`registry.py` | 未知 protocol fast-fail；可解析 `openai_compatible_chat` |
| **4B** | OpenAI-compatible 迁入适配器 | `providers/openai_compatible_chat.py`；`openai_compat.py` 变兼容门面 | 现有公开 API 行为不变；全量 openai_compat 测试绿 |
| 4C（可选） | generate/agents 经 registry 取 adapter | 调用方改 import | 留待 T-805 前按需；本卡不强制 |

## 强制规则

1. OpenAI-compatible Chat Completions 行为与错误语义不得回退（T-802 契约）。
2. 未知 / 未实现 protocol → `AppError`（如 `provider_capability_unsupported`），禁止静默回退到兼容层。
3. 本任务不并行启动 T-805/T-807。
4. `STREAM_TEXT_CHUNK_SIZE` 与 SSE 断流/非法帧语义保持不变。

## 明确不做（本卡）

- OpenAI Responses / Anthropic Messages / Gemini
- Anthropic prompt caching UI/开关
- generation metadata / usage ledger / 定价
- 重写 generate 消息形状为完整 Canonical Message 业务路径

## 验收命令

```powershell
cd backend
python -m pytest tests/test_openai_compat.py tests/test_llm_protocol_kernel.py tests/ -q
```

## 完成记录

### 4A / 4B（已完成）

- 新增 `types.py`（ProtocolId / GenerationConfig / WireRequest / Usage）、`protocol.py`（ProviderAdapter）、`registry.py`（`get_adapter`）。
- 实现迁入 `providers/openai_compatible_chat.py`；`OpenAICompatibleChatAdapter` 实现 list/complete/stream/build_request/decode_usage。
- `openai_compat.py` 变为稳定 ABI 再导出门面；业务调用方未改。
- 未知 protocol → `provider_capability_unsupported`；空 protocol → `config_missing`。
- 测试：`test_llm_protocol_kernel.py`；`test_openai_compat` HTTP mock 指向 provider 模块。
- 门禁：后端 226 passed。
