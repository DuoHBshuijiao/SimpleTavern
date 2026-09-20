# SimpleTavern 文档入口

本目录用于让 AI 在无完整聊天上下文时继续推进 `v0.500 -> v1.000` 稳定化工作。

## 测试策略（强制）

仓库内**不再包含** pytest / Vitest / Playwright 或任何自动化测试流程、门禁命令、`data-testid` 或断言代码。

- 后端接口规范：`docs/specs/BACKEND-API.md`
- 前端功能与可见控件：`docs/specs/FRONTEND-FEATURES.md`
- 黑盒用例由仓库外的代理团队只根据上述文档编写，**不接触本仓库源码**。
- 历史任务卡里的 `python -m pytest` / `npm run test` **已作废**，不要执行，也不要再加回来。
- 产品里的「测模型」「测音色」是连通性探测 API，不是自动化测试。

## 并行沙箱（黑盒点按）

完整操作说明见 [`docs/SANDBOX.md`](SANDBOX.md)。摘要：仓库根目录 `python sandbox.py`，浏览器打开 `http://127.0.0.1:9181`；数据在 `data-sandbox/`，不写生产 `data/`。

## 下一步阅读顺序

1. 先读 `docs/state/CURRENT.md`，确认当前任务。
2. 改接口或界面时，同步更新 `docs/specs/BACKEND-API.md` 或 `docs/specs/FRONTEND-FEATURES.md`。
3. 读 `docs/01-ROADMAP.md` 了解版本范围。
4. 架构契约可读 `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`。
5. 完成后更新 `docs/state/LAST_HANDOFF.md`。

## 文档职责

- `docs/SANDBOX.md`：并行沙箱启动、端口、数据隔离与浏览器点按。
- `docs/specs/BACKEND-API.md`：全部后端 HTTP/SSE 功能与数据规范。
- `docs/specs/FRONTEND-FEATURES.md`：前端功能分区与可见控件清单。
- `docs/01-ROADMAP.md`：版本目标、纳入范围、推迟范围。
- `docs/02-BACKLOG.md`：可执行任务池和优先级。
- `docs/RELEASE-v0.500.md`：v0.500 发布摘要（其中 pytest/vitest 命令已作废）。
- `docs/state/CURRENT.md`：唯一当前任务指针。
- `docs/state/LAST_HANDOFF.md`：给下一轮 AI 的最短交接。
- `docs/tasks/*.md`：历史任务卡；verify 段中的自动化测试命令不要再跑。

## 人类报告规则

面向人类只报告三件事：完成了什么、对照规格文档核对了什么、下一轮 AI 应读哪篇文档。不要再报告 pytest/vitest 条数。
