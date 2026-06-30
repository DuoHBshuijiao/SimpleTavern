# T-210 v0.700 ChatPage composable 第二批

- status: done
- area: frontend
- theme: 低风险 + 中风险 composable 提炼（行为不变）

## 已完成

1. `useMessageListEnterAnimations` + 单测
2. `useGlobalEscapeStack` / `createCloseTopOverlayHandler` + 单测
3. `useMainChatReasoning` + 单测
4. `useChatHeaderLayout` + 单测（顶栏 morph、高度测量、TTS/Agent 顶栏控件）
5. `useChatFabSeparation` + 单测（主区左缘测量、FAB 碰撞分离）

## 边界

- 生成/SSE orchestration、`GenerationDeferState` 仍属 v0.700 内但排在本批之后（T-212+）。
