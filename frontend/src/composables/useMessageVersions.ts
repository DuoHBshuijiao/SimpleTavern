/**
 * useMessageVersions - 消息版本管理
 * 
 * 负责消息重写时的多版本管理和切换功能
 */
import { ref } from 'vue'
import type { ChatMessage } from '../types/models'

export function useMessageVersions() {
  // 存储每个消息的多个版本：messageId -> versions[]
  const messageVersions = ref<Map<string, string[]>>(new Map())
  // 存储每个消息当前显示的版本索引：messageId -> currentVersionIndex
  const messageVersionIndex = ref<Map<string, number>>(new Map())
  // 存储消息ID映射：originalMessageId -> currentMessageId（用于重写后关联）
  const messageIdMap = ref<Map<string, string>>(new Map())

  /**
   * 获取消息的原始 ID（处理重写后的 ID 映射）
   */
  function getOriginalMessageId(messageId: string): string {
    for (const [originalId, currentId] of messageIdMap.value.entries()) {
      if (currentId === messageId) {
        return originalId
      }
    }
    return messageId
  }

  /**
   * 获取消息的显示内容（考虑版本切换）
   */
  function getDisplayContent(message: ChatMessage): string {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    if (!versions || versions.length === 0) {
      return message.content
    }
    const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
    return versions[currentIndex] ?? message.content
  }

  /**
   * 检查消息是否有多个版本
   */
  function hasMultipleVersions(message: ChatMessage): boolean {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    return versions ? versions.length > 1 : false
  }

  /**
   * 获取当前版本索引
   */
  function getCurrentVersionIndex(message: ChatMessage): number {
    const messageId = getOriginalMessageId(message.id)
    return messageVersionIndex.value.get(messageId) ?? 0
  }

  /**
   * 获取版本总数
   */
  function getVersionCount(message: ChatMessage): number {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    return versions ? versions.length : 1
  }

  /**
   * 保存消息内容到版本历史
   */
  function saveVersion(messageId: string, content: string) {
    const versions = messageVersions.value.get(messageId) || []
    if (!versions.includes(content)) {
      versions.push(content)
    }
    messageVersions.value.set(messageId, versions)
    messageVersionIndex.value.set(messageId, versions.length - 1)
  }

  /**
   * 添加新版本并设置 ID 映射
   */
  function addNewVersion(originalMessageId: string, newMessageId: string, newContent: string) {
    const versions = messageVersions.value.get(originalMessageId) || []
    if (newContent && !versions.includes(newContent)) {
      versions.push(newContent)
    }
    
    // 如果新消息ID不同，创建映射关系
    if (newMessageId !== originalMessageId && !newMessageId.startsWith('local_')) {
      messageIdMap.value.set(originalMessageId, newMessageId)
    }
    
    messageVersions.value.set(originalMessageId, versions)
    messageVersionIndex.value.set(originalMessageId, versions.length - 1)
  }

  /**
   * 切换到上一个版本
   * @returns 新版本的内容，用于更新消息
   */
  function switchToPreviousVersion(message: ChatMessage): string | null {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    if (!versions || versions.length <= 1) return null
    
    const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
    const newIndex = currentIndex > 0 ? currentIndex - 1 : versions.length - 1
    messageVersionIndex.value.set(messageId, newIndex)
    
    return versions[newIndex] ?? null
  }

  /**
   * 切换到下一个版本
   * @returns 新版本的内容，用于更新消息
   */
  function switchToNextVersion(message: ChatMessage): string | null {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    if (!versions || versions.length <= 1) return null
    
    const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
    const newIndex = currentIndex < versions.length - 1 ? currentIndex + 1 : 0
    messageVersionIndex.value.set(messageId, newIndex)
    
    return versions[newIndex] ?? null
  }

  /**
   * 清理消息的其他版本，只保留当前显示的版本
   * @returns 当前版本的内容
   */
  function cleanupVersions(message: ChatMessage): string {
    const messageId = getOriginalMessageId(message.id)
    const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
    const versions = messageVersions.value.get(messageId)
    
    if (versions && versions.length > 1) {
      const currentContent = versions[currentIndex] ?? message.content
      messageVersions.value.set(messageId, [currentContent])
      messageVersionIndex.value.set(messageId, 0)
      return currentContent
    }
    
    return message.content
  }

  /**
   * 清除指定消息的版本历史
   */
  function clearVersions(messageId: string) {
    const originalId = getOriginalMessageId(messageId)
    messageVersions.value.delete(originalId)
    messageVersionIndex.value.delete(originalId)
    
    // 清理映射
    for (const [origId, currId] of messageIdMap.value.entries()) {
      if (origId === originalId || currId === messageId) {
        messageIdMap.value.delete(origId)
      }
    }
  }

  /**
   * 清除所有版本历史
   */
  function clearAll() {
    messageVersions.value.clear()
    messageVersionIndex.value.clear()
    messageIdMap.value.clear()
  }

  return {
    // 状态
    messageVersions,
    messageVersionIndex,
    messageIdMap,
    
    // 方法
    getOriginalMessageId,
    getDisplayContent,
    hasMultipleVersions,
    getCurrentVersionIndex,
    getVersionCount,
    saveVersion,
    addNewVersion,
    switchToPreviousVersion,
    switchToNextVersion,
    cleanupVersions,
    clearVersions,
    clearAll,
  }
}

export type UseMessageVersions = ReturnType<typeof useMessageVersions>
