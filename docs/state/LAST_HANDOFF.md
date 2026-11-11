# Last Handoff

## 当前交接（2026-11-08）

- 在做 v1.000 发布验收，清单是 `docs/tasks/T-814-v1000-release-acceptance.md`。新功能已冻结，只修问题。全部提交在本地 master，没有推送（推送由作者决定）。
- 这一批：T-832（Bedrock Converse、Mistral Conversations、Vertex 上的 Claude，eventstream 解析），模糊改用 Tailwind 工具类，验收中找到的 10 个缺陷都已修复并做了对照，清单的“问题记录”里有列表。
- 验证方式改为两套黑盒检查：`tools/api-check/`（接口，依据官方文档和规格）、`tools/ui-check/`（界面，构建产物和开发服务器各跑）。实现和验证分开写，每项检查都有能失败的对照。全量结果在清单的“验收记录”里。
- 测不到的：真实上游（Bedrock 和 Mistral 没有账号，Vertex 上的 Claude 作者没有开通）、真实 GPU 下模糊和 WebGPU 的开销、真机字体、作者最长的真实会话、真实 OAuth 授权流程。
- 下一步：作者手测三晚和 Vertex 实测；发现的问题按“修复、对照、重跑两套检查”处理。手测通过后改 `version.py` 为 v1.000，发布动作每一步由作者确认。
- 注意：模糊只能用 Tailwind `backdrop-*` 工具类，手写 `backdrop-filter` 构建后会失效（DESIGN.md 的 The Tailwind Blur Rule）；回归沙箱从真实 `data/` 只读复制并清空密钥，作者实例在 9081/9091。

## 上一次交接（2026-10-22）

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
