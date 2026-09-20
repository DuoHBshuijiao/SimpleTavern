# T-808 v0.800 本地定价引擎 + 统计 API 与设置页仪表盘

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**
- area: backend `services/pricing.py` + `routes/usage.py` + SettingsDrawer 用量摘要
- priority: P1
- theme: 云端 cost 不被覆盖；未知不计 0；会话/全局/按模型可解释
- depends_on: T-807（完成）

## 目标

在 T-807 账本之上提供本地价格表、汇总 API 与设置页仪表盘。统计只读 ledger，不扫全部 chat JSON。

## 完成定义

- 定价优先级：供应商 cloud cost → resolvedModel 精确 ID → provider+别名（最短 3 字符）→ 正则 alias（有效部分最短 3 字符）→ 用户覆盖 → unknown。
- 禁止「克」这类单字自动映射；用户规则 id 不得以 `catalog:` 开头。
- 云端 `cost.source=provider` 不被本地估算覆盖；估算仅写入 `estimatedAmount` / `pricingRuleId`。
- API：`GET /api/usage/summary|models|events`、`GET /api/pricing/rules`、`PUT /api/pricing/rules/{rule_id}`。
- 设置「应用与更新」accordion 内、成本计算器按钮上方：当前会话/全局、时间范围、token/缓存/成本来源/延迟、按模型表。
- 无活动会话时禁用「当前会话」并说明原因。非 USD 分币种展示，不做无汇率来源的换算。

## 路径

- `backend/app/services/pricing.py`、`backend/app/routes/usage.py`
- `data/pricing_rules.json`（用户覆盖）；目录价格只读
- `frontend/src/api/usage.ts`、`frontend/src/components/settings-drawer/SettingsDrawerGlobalUsageSummary.vue`
