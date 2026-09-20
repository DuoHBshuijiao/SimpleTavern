# Last Handoff

- last_task: 并行沙箱（独立 data + 浏览器点按）
- status: 完成
- summary: `SIMPLETAVERN_DATA_DIR` 可切数据目录；`python sandbox.py` 在 9181/9191 启动沙箱并只复制 `settings.json`。黑盒点按打开 `http://127.0.0.1:9181`，对照 `docs/specs/`。
- known_gap:
  - T-832 Bedrock eventstream / Converse / Mistral Conversations / Vertex rawPredict → P1
  - T-806-6C Responses 内建 web_search（v0.800）
  - 真实 API Key 缓存探测已搁置
  - `version.py` 仍为 `v0.810`（发版再改）
- verification:
  - 规格文档：`docs/specs/BACKEND-API.md`（107 路径 / 132 操作）、`docs/specs/FRONTEND-FEATURES.md`（746 条可见控件）
  - 仓库内不再运行 pytest / `npm run test`；`frontend npm run build` 仍可用于构建核对
- version_note: `backend/app/version.py` = `v0.810`
- next_read:
  1. `docs/SANDBOX.md`
  2. `docs/specs/BACKEND-API.md`
  3. `docs/specs/FRONTEND-FEATURES.md`
- next_implementation: 按用户指定继续功能；不要把测试框架加回仓库。
