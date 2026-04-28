/**
 * Composables模块导出
 *
 * 统一导出所有Vue Composables，方便其他模块导入使用。
 *
 * 主要功能：
 *    - 导出流式输出处理：useStreamOutput
 *    - 导出消息版本管理：useMessageVersions
 *    - 导出群聊逻辑：useGroupChat
 *    - 导出聊天助手逻辑：useAssistant
 *    - 导出聊天操作逻辑：useChatActions
 *
 * 文件关系：
 *    - 被导入：被components、views等模块导入用于使用composables
 *    - 导入：导入各个composables文件
 *    - 依赖：依赖vue
 *    - 位置：Composables层，提供可复用的组合式函数
 */
export { useStreamOutput } from './useStreamOutput'
export type { UseStreamOutput, StreamOutputOptions, StreamOutputState } from './useStreamOutput'

export { useMessageVersions } from './useMessageVersions'
export type { UseMessageVersions } from './useMessageVersions'

export { useGroupChat } from './useGroupChat'
export type { UseGroupChat, GroupChatDeps } from './useGroupChat'

export { useAssistant } from './useAssistant'
export type {
  UseAssistant,
  AssistantMessage,
  AssistantScope,
  AssistantSettings,
  UseAssistantOptions,
  SendAssistantMessageOptions,
} from './useAssistant'
export { AUTO_MEMORY_SUMMARY_USER_MESSAGE } from './useAssistant'

export { useChatActions } from './useChatActions'
export type { UseChatActions, ChatActionsDeps } from './useChatActions'

export { useAppFont, applyFont } from './useAppFont'
export { useSettingsImport } from './useSettingsImport'
export { useViewportNarrowPortrait } from './useViewportNarrowPortrait'
export { usePreferHoverChrome } from './usePreferHoverChrome'
export type { SettingsImportResult } from './useSettingsImport'

export { useNotify, notifyMessage, notifyConfirm } from './useNotify'
export type { NotifyConfirmVariant, NotifyItem } from './useNotify'
