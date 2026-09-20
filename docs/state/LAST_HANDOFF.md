# Last Handoff

- last_task: T-806-6C Responses 内建 web_search + T-807 usage ledger；前端控件清单 746/725 澄清为 649
- status: 编码完成，未 git add / commit / push（由人类执行）
- summary: 主聊天 `webSearchEnabled` 在 `openai_responses` 上走 `{type:web_search}`，其它协议仍用 Tavily/博查循环。助手消息写 `generationMetadata`，账本 `data/usage/YYYY-MM.jsonl`。点按清单以 `FRONTEND-FEATURES.md` 649 为准。
- known_gap:
  - T-808～T-813（v0.800 P1）
  - T-814 全链路规格核对（仓库外黑盒）
  - T-832 Bedrock eventstream / Converse / Mistral / Vertex → v0.820 P1
  - 真实 API Key 缓存探测已搁置
  - `version.py` 仍为 `v0.810`（发版再改）
- verification:
  - 规格文档：`docs/specs/BACKEND-API.md`、`docs/specs/FRONTEND-FEATURES.md`（649 条可点/可填控件；旧称 746/725 作废）
  - 仓库内不再运行 pytest / `npm run test`；`frontend npm run build` 仍可用于构建核对
- version_note: `backend/app/version.py` = `v0.810`
- next_read:
  1. `docs/specs/BACKEND-API.md`
  2. `docs/specs/FRONTEND-FEATURES.md`
  3. `docs/SANDBOX.md`
- next_implementation: v0.800 P1 从 T-808 开始；不要把测试框架加回仓库；不要启动 v0.900。
