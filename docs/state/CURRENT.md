# 当前任务

- current: `v0.700`
- status: in-progress
- next_read: `docs/tasks/T-210-v0700-chat-composables-phase2.md`（中风险 composable）→ `T-211` SettingsDrawer 拆分
- goal: v0.700 全量完成——前端拆分 + 全面 UI/动画 + 可观测性；v0.800 专责后端性能。

## 完成度（约 62%）

- 已完成：T-201~209（测试基座、6 composable、数据完整性、import warning、UI/Impeccable 扫尾）
- 进行中：T-210 第二批 composable（入场动画/Esc/思考链已完成；顶栏布局/FAB 待做）
- 待做：T-211~214（SettingsDrawer/ChatPage 拆分、ChatInput 动效、收尾）

## 验证（每批后）

- `cd frontend && npm run test && npm run build`
- `npx impeccable detect src/components/chat`（ChatInput margin 属 T-213）
- `cd backend && python -m pytest tests/ -q`（可观测性改动时）
