# 当前任务

- current: `v0.700`
- status: in-progress
- next_read: `docs/tasks/T-211-v0700-settings-drawer-split.md`（Global Tab accordion）
- goal: v0.700 全量完成——前端拆分 + 全面 UI/动画 + 可观测性；v0.800 专责后端性能。

## 完成度（约 68%）

- 已完成：T-201~210、T-209、T-211 首批（3 Teleport 子组件）
- 进行中：T-211 SettingsDrawer 继续拆分
- 待做：T-212~214（ChatPage 子模块/生成流、ChatInput 动效、收尾）

## 验证（每批后）

- `cd frontend && npm run test && npm run build`
- `npx impeccable detect src/components/chat`（ChatInput margin 属 T-213）
- `cd backend && python -m pytest tests/ -q`（可观测性改动时）
