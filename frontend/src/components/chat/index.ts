/**
 * 聊天组件模块导出
 *
 * 统一导出所有聊天相关的组件，方便其他模块导入使用。
 *
 * 主要功能：
 *    - 导出侧边栏组件：ChatSidebar
 *    - 导出消息列表组件：MessageList
 *    - 导出聊天输入组件：ChatInput
 *    - 导出助手面板组件：AssistantPanel
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue等模块导入用于使用聊天组件
 *    - 导入：导入各个聊天组件文件
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供聊天相关组件的统一入口
 */
export { default as ChatSidebar } from './ChatSidebar.vue'
export { default as MessageList } from './MessageList.vue'
export { default as ChatInput } from './ChatInput.vue'
export { default as AssistantPanel } from './AssistantPanel.vue'
export { default as AssistantThread } from './AssistantThread.vue'
export { default as MvuPanel } from './MvuPanel.vue'
export { default as InitialStateEditor } from './InitialStateEditor.vue'
