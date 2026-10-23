# Last Handoff

## 当前交接（2026-10-22）

- 首轮跨端联网/订阅代码已落地，未 git add/commit/push。先读 `docs/tasks/2026-10-22-native-web-subscription.md` 及规格文档最新增补。
- 官方 `openai-chatgpt` 使用 SIWC 动态注册/公开 Responses，旧 Codex 独立保留；Grok 为公开客户端兼容流程。主聊天和助手接入 DeepSeek Search/Fetch、Claude 原生抓取和 GPT 联动网页动作。
- Desktop 前端构建/类型检查通过；后端全量 Python 语法和相关模块导入完成；Android Debug 构建通过。首次前端构建发现的旧重复 geminiSearch 字段已去重。
- 未完成：可核实的 SIWC/Grok 额度读取接口；当前 unsupported 加管理用量链接。真实账号扣额、联网调用、Android 设备浏览器回调与完整产品 UI 不在已验收证据中。
- 遵守仓库策略，未新增测试框架、断言或自动化门禁。下一步外部验收按两端计划中的场景进行，不将构建通过宣称为真实上游通过。

## 历史交接

- last_task: T-808～T-813（定价引擎/用量 UI、Brave+原生联网、领域性能说明、orphan/锁超时、`useChatGeneration`、迁移与隐私）
- status: 编码完成，未 git add / commit / push（由人类执行）
- summary: 设置页用量摘要在成本计算器上方；Brave 独立搜索与 Anthropic/Gemini 原生联网分轨；health 暴露锁/TTS/正则/迁移警告；世界书孤儿扫描；ChatPage 生成 SSE 抽到 `useChatGeneration`，停止或失败不丢消息；账本脱敏 + `migration_warnings.jsonl`。点按清单以 `FRONTEND-FEATURES.md` **654** 为准。
- known_gap:
  - T-814 全链路规格核对（仓库外黑盒）——本批按指令未做
  - 未启动 v0.900，未做 bug/优化扫尾
  - T-832 Bedrock eventstream / Converse / Mistral / Vertex → v0.820 P1
  - 真实 API Key 缓存探测已搁置
  - `version.py` 仍为 `v0.810`（发版再改）
- verification:
  - 规格文档：`docs/specs/BACKEND-API.md`（112/137）、`docs/specs/FRONTEND-FEATURES.md`（654）
  - 仓库内不再运行 pytest / `npm run test`；`frontend npm run build` 仍可用于构建核对
- version_note: `backend/app/version.py` = `v0.810`
- next_read:
  1. `docs/specs/BACKEND-API.md`
  2. `docs/specs/FRONTEND-FEATURES.md`
  3. `docs/SANDBOX.md`
- next_implementation: T-814 由测试组对照规格做仓库外黑盒；不要把测试框架加回仓库；不要启动 v0.900。
