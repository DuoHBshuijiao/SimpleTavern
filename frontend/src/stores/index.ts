/**
 * Store模块导出
 *
 * 统一导出所有Pinia Store，方便其他模块导入使用。
 *
 * 主要功能：
 *    - 导出设置Store：useSettingsStore
 *    - 导出角色Store：useCharactersStore
 *    - 导出聊天Store：useChatsStore
 *
 * 文件关系：
 *    - 被导入：被composables、components、views等模块导入用于访问Store
 *    - 导入：导入settings.ts、characters.ts、chats.ts中的Store
 *    - 依赖：依赖pinia
 *    - 位置：Store层，提供全局状态管理的统一入口
 */

export { useSettingsStore } from './settings'
export { useCharactersStore } from './characters'
export { useChatsStore } from './chats'
export { useUiStore } from './ui'
export { useCharacterSidebarRecencyStore } from './characterSidebarRecency'


