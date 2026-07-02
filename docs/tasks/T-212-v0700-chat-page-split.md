# T-212 v0.700 ChatPage 子模块拆分

- status: completed
- area: frontend
- theme: 角色编辑弹窗 UI + 局部状态 composable 迁出 ChatPage
- coverage: `docs/tasks/T-212-coverage-matrix.md`

## 已完成

1. `useCharacterEditor.ts`：额外首句、绑定世界书、打开/关闭时状态重置
2. `CharacterEditorModal.vue`：角色编辑弹窗 UI（含工作区助手面板）
3. `ChatPage.vue` 接入 modal；工作区 ref 通过父组件 bind 回调绑定（避免 reactive provide 解包 ref）
4. `PersonaEditorModal.vue`、`PersonaSwitchConfirmModal.vue`：身份编辑与切换确认弹窗
5. `useEmbeddedAvatarImport.ts` + `EmbeddedCardConfirmModal.vue`：PNG 内嵌卡 / ST 预览确认流
6. `AssistantSettingsModal.vue`：聊天助手设置弹窗
7. `useGenerationDeferState.ts`：流式延后删除 / 重写合并 / 保存并发送上下文

## 推迟到 v0.800

8. 生成/SSE orchestration 主体（见 `docs/tasks/T-800-v0800-backend-performance.md` T-801）

## 约束

- 角色保存/取消/助手工作区生命周期仍由 ChatPage + `useChatActions` / `useAssistant` 编排
- DOM ref 不通过 `reactive` provide 暴露，使用 bind 回调或 props 函数

## verify

```powershell
cd frontend
npm run test
npm run build
```
