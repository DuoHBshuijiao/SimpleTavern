# T-812 v0.800 ChatPage SSE → `useChatGeneration`

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。

- status: **done**
- area: `frontend/src/composables/useChatGeneration.ts` + `ChatPage.vue`
- priority: P1
- theme: 页面只保留编排；统一消费 meta/usage/done/error；停止/失败不丢消息
- depends_on: T-801、T-807

## 目标

把主聊天（单聊 / 群聊 / 插话 / 重写 / 图片回退）的 SSE 处理抽到 composable。写作辅助 `draft-help` 仍留在页面（独立状态机）。

## 完成定义

- 统一 handler：`meta` 合并进 `generationMetadata`；`usage` 补丁消息；`delta`/`reasoning`；`done` 写 usage+metadata；`error` 结束思考相位。
- 停止时忽略后续 `delta`，保留已有正文。
- `finally`：停止或失败走 `persistLocalStreamingMessages`，不 `chats.load` 冲掉本地流。
- ChatPage 继续负责发送、群聊轮次、插话、重写锚点与错误栈。

## 路径

- `frontend/src/composables/useChatGeneration.ts`
- `frontend/src/views/ChatPage.vue`
- `frontend/src/composables/index.ts`
