# 当前任务

- current: 原生联网与订阅账号接入（2026-10-22，首轮代码与构建完成，真实账号验收及额度接口待补）
- feature_plan: `docs/tasks/2026-10-22-native-web-subscription.md`；官方 Sign in with ChatGPT 替代新增功能中的 Codex 后端接入思路，历史 Codex 预设独立兼容。
- status: 当前功能按 feature_plan 核对；历史 v0.800 仍待 T-814 仓库外黑盒发布核对，未启动 v0.900。
- next_read: `docs/specs/BACKEND-API.md`、`docs/specs/FRONTEND-FEATURES.md`、`docs/SANDBOX.md`
- goal: 后续只做仓库外黑盒测试；实现侧不再新增断言、门禁或测试框架

## 版本宣告

- v0.800 P1：T-808 定价/统计 UI、T-809 Brave+Anthropic/Gemini 原生联网、T-810 领域性能说明、T-811 世界书孤儿与锁超时、T-812 `useChatGeneration`、T-813 迁移警告与账本脱敏。
- v0.800 P0 剩余：T-814 全链路规格核对。
- v0.820 P0：T-830 OAuth、T-831 成员级思考/Fast 此前已落地。
- T-832、真实 Key 缓存探测不在本批。
- 发版时再改 `version.py`（仍为 `v0.810`）。

## 必读

- `docs/SANDBOX.md`（并行沙箱用法）
- `docs/00-INDEX.md`（测试策略）
- `docs/specs/BACKEND-API.md`（112 路径 / 137 操作）
- `docs/specs/FRONTEND-FEATURES.md`（654 条可点/可填控件）
