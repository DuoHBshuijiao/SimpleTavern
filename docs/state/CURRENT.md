# 当前任务

- current: `v0.700`
- status: done
- next_read: `docs/01-ROADMAP.md`
- goal: v0.700 完成——组件化/可观测性 + UI/UX 一致性批次（Impeccable 检测通过 ChatPage/ChatSidebar 关键项）。

## 验证

- `cd frontend && npm run test` 通过，18 文件 88 tests；`npm run build` 通过。
- `cd backend && python -m pytest tests/ -q` 通过，114 tests。
- `npx impeccable detect frontend/src/views/ChatPage.vue frontend/src/components/chat/ChatSidebar.vue` 无 anti-pattern。

## 完成后

下一轮 AI 读 `docs/01-ROADMAP.md` 的 v0.800+ 方向。
