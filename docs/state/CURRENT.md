# 当前任务

- current: `v0.700` → **收尾完成，下一版本 v0.800**
- status: completed
- next_read: `docs/tasks/T-800-v0800-backend-performance.md`
- goal: v0.800 合并 SSE composable + 后端性能 + 完整性 orphan 扩展；多厂商协议 v0.900+

## v0.700 完成度（100% 前端范围）

- T-201~214 全部完成（组件化、UI/动画、前端可观测性）
- ChatPage 弹层/composable 拆分完成；SSE 主体 **有意留 v0.800**
- 验证：`frontend npm run test` + `npm run build`；`backend pytest`

## v0.700 边界（已遵守）

- ✅ 前端组件化、Impeccable/motion、integrity/import 前端提示
- ❌ 不在本版：SSE 主体 composable、后端性能、多厂商协议、导出 API warnings 扩展
