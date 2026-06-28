# T-003 前端 P0 修复

- status: done
- area: frontend
- priority: P0

## read_first

- `frontend/src/components/SettingsDrawer.vue`
- `frontend/src/views/ChatPage.vue`
- `frontend/src/components/AppNotificationHost.vue`
- `frontend/src/composables/useNotify.ts`
- `frontend/src/utils/contentRegex.ts`
- `frontend/src/components/chat/MessageList.vue`
- `frontend/src/styles/variables.css`

## acceptance

- 设置抽屉关闭时会保护未保存更改。
- 设置抽屉打开时，外部 chat overrides 更新不会覆盖正在编辑的 MVU 草稿。
- 抽屉、modal、助手面板、MVU 面板的叠层不会互相遮挡关键交互。
- Esc 可以按顶层优先级关闭确认框、modal、drawer 或搜索。
- 高风险 `window.confirm` 路径改用应用内确认框。
- 前端正文正则显示语义与后端保持一致。
- MessageList markdown HTML cache 有上限。

## verify

```powershell
cd E:\SimpleTavern\frontend
npm run test
npm run build
```

## next_hint

完成后读取 `docs/tasks/T-004-backend-p0.md`。
