# T-212 v0.700 ChatPage 角色编辑子模块拆分

- status: in-progress
- area: frontend
- theme: 角色编辑弹窗 UI + 局部状态 composable 迁出 ChatPage

## 已完成

1. `useCharacterEditor.ts`：额外首句、绑定世界书、打开/关闭时状态重置
2. `CharacterEditorModal.vue`：角色编辑弹窗 UI（含工作区助手面板）
3. `ChatPage.vue` 接入 modal；工作区 ref 通过父组件 bind 回调绑定（避免 reactive provide 解包 ref）
4. `PersonaEditorModal.vue`、`PersonaSwitchConfirmModal.vue`：身份编辑与切换确认弹窗

## 待做

5. 内嵌 PNG/ST 确认弹层与头像裁剪流程整理
6. 生成/SSE orchestration 后拆（`GenerationDeferState`，低风险 composable 优先）

## 约束

- 角色保存/取消/助手工作区生命周期仍由 ChatPage + `useChatActions` / `useAssistant` 编排
- DOM ref 不通过 `reactive` provide 暴露，使用 bind 回调或 props 函数

## verify

```powershell
cd frontend
npm run test
npm run build
```
