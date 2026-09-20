# T-810 v0.800 分领域性能说明与异常可见

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**（说明既有 T-803 基线 + 把后台异常挂到 health/设置页；**未发明无测量的加速**）
- area: generate / assistant / MVU / KG / regex / TTS
- priority: P1
- theme: 先测量再优化；异常必须可定位
- depends_on: T-801、T-803

## 目标

把各领域已有性能数字写成可对照说明，并让锁/巡检/TTS 失败出现在 health 或设置页。本卡不引入未测量的新加速路径。

## 既有基线（T-803，本卡沿用）

| 路径 | 数字 | 回归门槛 |
|------|------|----------|
| fork 冷重建 1000 chats / 99 forks | 410.05 ms | `< 5000 ms` |
| chat_path 冷重建 1000（50×20） | 103.11 ms | `< 1000 ms` |
| chat_path 暖查找 ×1000 | 105.55 ms | `< 500 ms` |
| content-regex 冷扫 100 chats | 130.21 ms | `< 5000 ms` |
| content-regex 暖扫 100（mtime 跳过） | 16.54 ms | `< max(100, 冷×25%)` |
| generate prep（20 书/2 激活） | prepTotal ≈ 5.13 ms，只 load 激活书 | `< 2000 ms` |
| 共享 HTTP client | 进程内复用 + 默认 Timeout/Limits | 见 T-803-3A |

领域对应：

- Generate：prep 分段计时 + 世界书激活索引（T-803-3D）；SSE terminal error 已由 T-801 覆盖。
- Assistant / MVU / KG：工具与 Agent 失败走统一 AppError；KG 路由 chat fast-fail。
- Regex：`GET /api/content-regex/health` 与进程 `GET /api/health.contentRegex` 含扫描耗时与锁等待。
- TTS：缓存巡检失败写入 `ttsCache.lastError`；设置页缓存条展示该错误；`GET /api/tts/cache/stats` 同样返回 `lastError`。

## 本卡落地

- `GET /api/health` 增加 `locks`（含 timeoutCount / timeoutSec=30）、`contentRegex`、`ttsCache`、`migrationWarnings`。
- 不新增无前后数据的缓存/批处理/连接池改动。

## 明确不做

- 未测量的流式 chunk 策略、TTS 子进程池、Assistant schema 新缓存层。
- 仓库内自动化性能测试。
