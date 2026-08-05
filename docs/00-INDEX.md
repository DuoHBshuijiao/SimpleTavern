# SimpleTavern 文档入口

本目录用于让 AI 在无完整聊天上下文时继续推进 `v0.500 -> v1.000` 稳定化工作。

## 下一步阅读顺序

1. 先读 `docs/state/CURRENT.md`，确认当前任务（现为 v0.800 / T-804）。
2. 读 `docs/01-ROADMAP.md` 与 T-804 相关任务卡/设计规格（当前实施目标）。
3. 读 `docs/tasks/T-800-v0800-backend-performance.md`，了解全版本依赖与边界。
4. T-801/T-802 已完成：错误契约见 `T-801`；fallback 清单见 `docs/audits/v0800-backend-fallback-inventory.md`。
5. 架构契约读 `docs/superpowers/specs/2026-07-10-v0800-backend-trust-layer-design.md`。
6. 按任务内 `read_first` 阅读源码与契约文件。
7. 完成后更新当前任务、`docs/state/LAST_HANDOFF.md` 和必要的发布文档。

## 文档职责

- `docs/01-ROADMAP.md`：版本目标、纳入范围、推迟范围。
- `docs/02-BACKLOG.md`：可执行任务池和优先级。
- `docs/RELEASE-v0.500.md`：发布门禁、验证命令和 Release 摘要。
- `docs/state/CURRENT.md`：唯一当前任务指针。
- `docs/state/LAST_HANDOFF.md`：给下一轮 AI 的最短交接。
- `docs/tasks/*.md`：一次 AI 会话可完成的任务卡。

## 人类报告规则

面向人类只报告三件事：完成了什么、验证了什么、下一轮 AI 应读哪篇文档。代码细节和中间状态写入任务文件或 `LAST_HANDOFF`。
