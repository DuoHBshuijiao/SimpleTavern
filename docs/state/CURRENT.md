# 当前任务

- current: `v0.700`
- status: in-progress
- next_read: `docs/tasks/T-212-coverage-matrix.md` → T-212#8 或 T-213
- goal: v0.700 全量完成——前端拆分 + 全面 UI/动画 + 可观测性；v0.800 专责后端性能。

## 完成度（约 93%）

- 已完成：T-201~211、T-212 ChatPage 弹层/UI 拆分 + `useGenerationDeferState`（延后删除上下文）
- 进行中：T-212#8 SSE 主体拆分；T-213~214
- 覆盖率矩阵：`docs/tasks/T-212-coverage-matrix.md`

## 验证（每批后）

- `cd frontend && npm run test && npm run build`
