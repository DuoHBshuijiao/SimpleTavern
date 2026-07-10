# T-801 v0.800 Fast-Fail 错误基座

- status: ready
- area: backend + frontend error transport
- priority: P0（v0.800 第一批，阻塞其他任务）
- theme: 统一错误类型、REST/SSE 契约、requestId、用户可感知提示

## 目标

建立所有后端组件可复用的错误基础设施。此任务不负责一次性迁移全部 backend；它提供 T-802 所需的统一出口。

## read_first

- `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`
- `backend/app/main.py`
- `backend/app/routes/generate.py`（SSE `_sse` 与 event iterator）
- `backend/app/routes/assistant.py`
- `backend/app/routes/mvu.py`（已有结构化错误参考）
- `backend/app/llm/openai_compat.py`
- `frontend/src/api/http.ts`
- `frontend/src/api/sse.ts`
- `frontend/src/composables/useErrorStack.ts`

## 范围

### 后端

1. 新增统一 `AppError` / `ErrorEnvelope`。
2. 全局 FastAPI exception handler：
   - AppError
   - Pydantic/请求校验
   - HTTPException 兼容
   - 未处理异常（不泄露敏感堆栈给 UI）
3. requestId middleware：
   - 接受可信客户端 request ID 或生成新 ID
   - 响应 header 返回
   - 传入出站 HTTP log / usage trace
4. SSE helper：
   - `meta`
   - `error`（terminal）
   - `done`（success only）
5. provider/upstream 异常映射：
   - auth
   - quota/rate limit
   - timeout/network
   - invalid response/protocol
6. 安全 redaction：API Key、Authorization、cookie、完整敏感正文。

### 前端

1. `api/http.ts` 解析统一错误 envelope，抛出 typed error。
2. `api/sse.ts` 解析 terminal error。
3. `useErrorStack` 展示 message + suggestedAction，并保留 requestId 供复制。
4. 兼容旧裸字符串错误一个迁移周期。

## 明确不做

- 不在本任务接入 Anthropic/Gemini/Responses。
- 不重构所有 route；只迁最小示范路径：
  - `/llm/test-models`
  - 一条主聊天生成 REST/SSE 路径
  - 一条工具/搜索失败路径
- 不做自动 retry/fallback。

## 验收

- REST 失败不再返回 200/空数组冒充成功。
- SSE 失败仅发 terminal error，不再发 done。
- 错误栈能看到可读 message、建议操作、requestId。
- 日志含 requestId 且敏感字段已脱敏。
- 现有成功路径行为不变。

## 测试

### 后端

- AppError → HTTP status/envelope。
- 未处理异常 → generic 500 + requestId。
- 401/429/timeout 映射。
- SSE error terminal，后续无 done。
- redaction。

### 前端

- REST typed error 解析。
- SSE terminal error 解析。
- suggestedAction/requestId 展示。
- 旧文本错误兼容。

## verify

```powershell
cd backend
python -m pytest tests/ -q

cd ..\frontend
npm run test
npm run build
```

## next

完成后进入 T-802：按模块迁移全 backend 的静默 fallback/catch。
