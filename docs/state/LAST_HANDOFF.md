# Last Handoff

- last_task: `T-803-3A-shared-http-client`
- status: completed（T-803 overall in-progress）
- summary: 文档收口 T-802→T-803；完成共享 HTTP client（3A），并迁移 openai_compat + web_search。
- code_changes:
  - 新增 `docs/tasks/T-803-v0800-perf-infra.md` 与基线矩阵。
  - 新增 `backend/app/services/http_client.py`：进程级 Async/Sync client、lifespan startup/shutdown、请求级 timeout 覆盖。
  - `openai_compat` / `web_search` 不再每次新建 httpx Client。
  - `main.py` lifespan 接入 startup/shutdown。
- known_gap:
  - T-803 3B/3C/3D 未开始（索引、scanner、generate profiling）。
  - TTS platform 仍为实例级 client（评估是否并入共享池）。
  - 前端 health UI、Qwen3/OmniVoice process health 同构仍待后续。
- verification:
  - `cd backend && python -m pytest tests/ -q` → 见本轮结果。
- version_note: `backend/app/version.py` 仍为 `v0.700`。
- next_read:
  1. `docs/tasks/T-803-v0800-perf-infra.md`
  2. `docs/tasks/T-800-v0800-backend-performance.md`
- next_implementation: T-803-3B chatId/fork 索引与 I/O。不要同时开始 T-804。
