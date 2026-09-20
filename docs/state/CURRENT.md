# 当前任务

- current: 无进行中的规格化任务（本批已完成 T-806-6C 与 T-807 编码，待人类提交）
- status: v0.800 P0 剩余 T-814 发布核对；P1 为 T-808～T-813。未启动 v0.900。
- next_read: `docs/specs/BACKEND-API.md`、`docs/specs/FRONTEND-FEATURES.md`、`docs/SANDBOX.md`
- goal: 后续只做仓库外黑盒测试；实现侧不再新增断言、门禁或测试框架

## 版本宣告

- v0.800 P0：T-806-6C Responses 内建 web_search、T-807 generation metadata + usage ledger 已编码。
- v0.820 P0：T-830 OAuth、T-831 成员级思考/Fast 此前已落地。
- T-832、真实 Key 缓存探测、T-808 定价 UI 不在本批。
- 发版时再改 `version.py`。

## 必读

- `docs/SANDBOX.md`（并行沙箱用法）
- `docs/00-INDEX.md`（测试策略）
- `docs/specs/BACKEND-API.md`
- `docs/specs/FRONTEND-FEATURES.md`
