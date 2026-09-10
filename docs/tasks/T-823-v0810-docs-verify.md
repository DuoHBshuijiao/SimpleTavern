# T-823 v0.810 文档、验证与发布收口

- status: **done**（自动化门禁已绿；`version.py` 已改为 `v0.810`；真实 key 探测已搁置）
- area: `docs/`、`CHANGELOG.md`、`README.md`、`backend/app/version.py`
- priority: P1
- depends_on: T-820 / T-821 / T-822 / T-824

## 前置（本轮已落）

- `01-ROADMAP.md` 新增 v0.810 定位 / 交付 / 边界；v0.800 段标注 6C 缩窄。
- `02-BACKLOG.md` 新增 v0.810 段与依赖图；v0.820 候选。
- 五张任务卡；`CURRENT.md` → `v0.810`；`LAST_HANDOFF.md`；`CHANGELOG.md` `## v0.810`。

## 收尾清单

- [x] 后端 `python -m pytest tests/ -q` 全绿（319 passed）
- [x] 前端 `npm run test`（131 passed）+ `npm run build` 全绿
- [x] 静态守卫：`.vue` 无裸 `title`（`ModelControlPanel` 改为 `aria-label`）；catalog 加载失败走 AppError
- [x] README API 预设章节：供应商目录 / 缓存策略 / 自动协议 / 模型控制面板
- [x] CHANGELOG 按批次登记
- [x] `LAST_HANDOFF.md` 记录未完成项（A3 已滑动；Bedrock 原生 eventstream 流式 fast-fail）
- [x] `version.py` 已改为 `v0.810`
- [ ] 手动：真实 key 缓存命中验证（Responses / Anthropic / Gemini / 百炼）——**已搁置**
