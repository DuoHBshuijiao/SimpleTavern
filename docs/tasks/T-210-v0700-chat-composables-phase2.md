# T-210 v0.700 ChatPage composable 第二批

- status: in-progress
- area: frontend
- theme: 低风险 composable 继续提炼（行为不变）

## 已完成

1. `useMessageListEnterAnimations` + 单测
2. `useGlobalEscapeStack` / `createCloseTopOverlayHandler` + 单测
3. `useMainChatReasoning` + 单测

## 待做

4. `useChatHeaderLayout` / `useChatFabSeparation`（中风险）

## 边界

- 生成/SSE orchestration、`GenerationDeferState` 仍属 v0.700 内但排在本批之后（T-212+）。
