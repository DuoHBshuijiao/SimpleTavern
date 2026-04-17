/**
 * useMessageVersions - 消息版本管理Composable
 *
 * 负责消息重写时的多版本管理和切换功能，支持查看和切换消息的不同版本。
 *
 * 主要功能：
 *    - 版本存储：存储每个消息的多个版本内容
 *    - 版本切换：在多个版本之间切换显示
 *    - ID映射：处理重写后消息ID的变化
 *    - 版本清理：清理不需要的版本历史
 *
 * 主要函数：
 *    - getOriginalMessageId: 获取消息的原始ID
 *    - getDisplayContent: 获取消息的显示内容（考虑版本）
 *    - hasMultipleVersions: 检查是否有多个版本
 *    - getCurrentVersionIndex: 获取当前版本索引
 *    - getVersionCount: 获取版本总数
 *    - saveVersion: 保存消息版本
 *    - addNewVersion: 添加新版本
 *    - switchToPreviousVersion: 切换到上一个版本
 *    - switchToNextVersion: 切换到下一个版本
 *    - cleanupVersions: 清理版本历史
 *    - clearVersions: 清除指定消息的版本
 *    - clearAll: 清除所有版本
 *
 * 实现原理：
 *    - 使用Map存储每个消息ID对应的版本数组
 *    - 使用Map存储每个消息当前显示的版本索引
 *    - 使用Map存储原始消息ID到当前消息ID的映射（处理重写后的ID变化）
 *    - 通过切换版本索引来切换显示的内容
 *
 * 文件关系：
 *    - 被导入：被composables/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入vue的ref、types/models.ts的ChatMessage类型
 *    - 依赖：依赖vue
 *    - 位置：Composables层，提供消息版本管理逻辑
 */
import { ref } from 'vue'
import type { ChatMessage } from '../types/models'

export function useMessageVersions() {
  // 存储每个消息的多个版本：messageId -> versions[]
  const messageVersions = ref<Map<string, string[]>>(new Map())
  // 存储每个消息各版本对应的思考内容：messageId -> reasoning[]（与 content 版本一一对应）
  const messageReasoningVersions = ref<Map<string, string[]>>(new Map())
  // 存储每个消息当前显示的版本索引：messageId -> currentVersionIndex
  const messageVersionIndex = ref<Map<string, number>>(new Map())
  // 存储消息ID映射：originalMessageId -> currentMessageId（用于重写后关联）
  const messageIdMap = ref<Map<string, string>>(new Map())

  /**
   * 获取消息的原始ID（处理重写后的ID映射）
   *
   * 当消息被重写后，新消息会有新的ID，但需要关联到原始消息的版本历史。
   * 通过messageIdMap查找当前ID对应的原始ID，如果找不到则返回原ID。
   *
   * @param {string} messageId - 当前消息ID
   * @returns {string} 原始消息ID
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
   *
   * 根据当前版本索引，从版本数组中获取要显示的内容。
   * 如果没有版本历史，则返回消息的原始内容。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {string} 要显示的内容
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
   * 获取消息当前显示版本对应的思考内容
   *
   * 切换消息版本时，思考内容随版本一起切换。
   *
   * @param {ChatMessage} message - 消息对象
   * @returns {string | undefined} 当前版本的思考内容，无则返回 undefined
   */
  function getDisplayReasoning(message: ChatMessage): string | undefined {
    const messageId = getOriginalMessageId(message.id)
    const reasonings = messageReasoningVersions.value.get(messageId)
    if (reasonings && reasonings.length > 0) {
      const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
      const content = reasonings[currentIndex]?.trim()
      if (content) return content
    }
    const persisted = (message.reasoningContent ?? '').trim()
    return persisted || undefined
  }

  /**
   * 检查消息是否有多个版本
   *
   * 判断消息是否有多个版本可以切换。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {boolean} 是否有多个版本
   */
  function hasMultipleVersions(message: ChatMessage): boolean {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    return versions ? versions.length > 1 : false
  }

  /**
   * 获取当前版本索引
   *
   * 获取消息当前显示的版本在版本数组中的索引。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {number} 当前版本索引（从0开始）
   */
  function getCurrentVersionIndex(message: ChatMessage): number {
    const messageId = getOriginalMessageId(message.id)
    return messageVersionIndex.value.get(messageId) ?? 0
  }

  /**
   * 获取版本总数
   *
   * 获取消息的版本总数，如果没有版本历史则返回1。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {number} 版本总数
   */
  function getVersionCount(message: ChatMessage): number {
    const messageId = getOriginalMessageId(message.id)
    const versions = messageVersions.value.get(messageId)
    return versions ? versions.length : 1
  }

  /**
   * 保存消息内容到版本历史
   *
   * 将消息内容添加到版本数组中（如果不存在），并保存该版本对应的思考内容。
   * 将当前版本索引设置为最新版本。
   *
   * @param {string} messageId - 消息ID
   * @param {string} content - 消息内容
   * @param {string} [reasoning] - 该版本对应的思考内容（可选）
   */
  function saveVersion(messageId: string, content: string, reasoning?: string) {
    const versions = messageVersions.value.get(messageId) || []
    let reasonings = messageReasoningVersions.value.get(messageId) || []
    const idx = versions.indexOf(content)
    if (idx === -1) {
      versions.push(content)
      reasonings.push(reasoning?.trim() ?? '')
    } else {
      while (reasonings.length <= idx) reasonings.push('')
      reasonings[idx] = reasoning?.trim() ?? ''
    }
    messageVersions.value.set(messageId, versions)
    messageReasoningVersions.value.set(messageId, reasonings)
    messageVersionIndex.value.set(messageId, versions.length - 1)
  }

  /**
   * 添加新版本并设置ID映射
   *
   * 当消息被重写后，添加新版本内容及对应思考内容，并建立原始ID到新ID的映射关系。
   * 如果新消息ID与原始ID不同且不是本地消息，则创建映射。
   *
   * @param {string} originalMessageId - 原始消息ID
   * @param {string} newMessageId - 新消息ID
   * @param {string} newContent - 新版本内容
   * @param {string} [newReasoning] - 新版本对应的思考内容（可选）
   */
  function addNewVersion(originalMessageId: string, newMessageId: string, newContent: string, newReasoning?: string) {
    const versions = messageVersions.value.get(originalMessageId) || []
    const reasonings = messageReasoningVersions.value.get(originalMessageId) || []
    if (newContent && !versions.includes(newContent)) {
      versions.push(newContent)
      reasonings.push(newReasoning?.trim() ?? '')
    }
    
    // 如果新消息ID不同，创建映射关系
    if (newMessageId !== originalMessageId && !newMessageId.startsWith('local_')) {
      messageIdMap.value.set(originalMessageId, newMessageId)
    }
    
    messageVersions.value.set(originalMessageId, versions)
    messageReasoningVersions.value.set(originalMessageId, reasonings)
    messageVersionIndex.value.set(originalMessageId, versions.length - 1)
  }

  /**
   * 切换到上一个版本
   *
   * 将版本索引减1，如果已经是第一个版本则循环到最后一个版本。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {string | null} 新版本的内容，用于更新消息显示；如果没有多个版本则返回null
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
   *
   * 将版本索引加1，如果已经是最后一个版本则循环到第一个版本。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {string | null} 新版本的内容，用于更新消息显示；如果没有多个版本则返回null
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
   *
   * 将版本数组缩减为只包含当前显示的版本，版本索引重置为0；思考内容数组同步裁剪。
   * 用于发送新消息前清理版本历史。
   *
   * @param {ChatMessage} message - 消息对象（来自types/models.ts）
   * @returns {string} 当前版本的内容
   */
  function normalizeVariantText(s: string | undefined | null): string {
    return String(s ?? '')
      .trim()
      .replace(/\r\n/g, '\n')
  }

  /**
   * 从服务端持久化的 greetingVariants 恢复多版本状态（单聊开场白）
   * @param preferredIndex 服务端保存的下标，避免与 content 重复时 indexOf 恒为 0
   */
  function hydrateGreetingVariants(
    messageId: string,
    variants: string[],
    currentContent: string,
    preferredIndex?: number | null,
  ) {
    const cleaned = variants
      .map((v) => (v == null ? '' : String(v)).trim())
      .filter((v) => v !== '')
    if (cleaned.length <= 1) return
    const originalId = getOriginalMessageId(messageId)
    messageVersions.value.set(originalId, [...cleaned])
    messageReasoningVersions.value.set(
      originalId,
      cleaned.map(() => ''),
    )
    let idx: number
    if (
      typeof preferredIndex === 'number' &&
      Number.isFinite(preferredIndex) &&
      preferredIndex >= 0 &&
      preferredIndex < cleaned.length
    ) {
      idx = preferredIndex
    } else {
      const curNorm = normalizeVariantText(currentContent)
      const found = cleaned.findIndex((v) => normalizeVariantText(v) === curNorm)
      idx = found < 0 ? 0 : found
    }
    messageVersionIndex.value.set(originalId, idx)
  }

  function cleanupVersions(message: ChatMessage): string {
    const messageId = getOriginalMessageId(message.id)
    const currentIndex = messageVersionIndex.value.get(messageId) ?? 0
    const versions = messageVersions.value.get(messageId)
    const reasonings = messageReasoningVersions.value.get(messageId)
    
    if (versions && versions.length > 1) {
      const currentContent = versions[currentIndex] ?? message.content
      messageVersions.value.set(messageId, [currentContent])
      const currentReasoning = reasonings && reasonings[currentIndex] !== undefined ? [reasonings[currentIndex]] : []
      messageReasoningVersions.value.set(messageId, currentReasoning)
      messageVersionIndex.value.set(messageId, 0)
      return currentContent
    }
    
    return message.content
  }

  /**
   * 更新当前显示版本的内容（用于编辑保存后同步版本列表）
   *
   * 当用户编辑并保存一条有多版本的消息时，将当前显示版本的内容更新为编辑后的内容。
   *
   * @param {string} messageId - 当前消息ID
   * @param {string} newContent - 编辑后的内容
   */
  function updateCurrentVersionContent(messageId: string, newContent: string) {
    const originalId = getOriginalMessageId(messageId)
    const versions = messageVersions.value.get(originalId)
    const currentIndex = messageVersionIndex.value.get(originalId) ?? 0
    if (versions && currentIndex >= 0 && currentIndex < versions.length) {
      versions[currentIndex] = newContent
      messageVersions.value.set(originalId, [...versions])
    }
  }

  /**
   * 清除指定消息的版本历史
   *
   * 清除指定消息的所有版本数据和ID映射。
   *
   * @param {string} messageId - 消息ID
   */
  function clearVersions(messageId: string) {
    const originalId = getOriginalMessageId(messageId)
    messageVersions.value.delete(originalId)
    messageReasoningVersions.value.delete(originalId)
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
   *
   * 清空所有消息的版本数据、版本索引和ID映射。
   * 用于重置状态。
   */
  function clearAll() {
    messageVersions.value.clear()
    messageReasoningVersions.value.clear()
    messageVersionIndex.value.clear()
    messageIdMap.value.clear()
  }

  return {
    // 状态
    messageVersions,
    messageReasoningVersions,
    messageVersionIndex,
    messageIdMap,
    
    // 方法
    getOriginalMessageId,
    getDisplayContent,
    getDisplayReasoning,
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
    updateCurrentVersionContent,
    hydrateGreetingVariants,
  }
}

export type UseMessageVersions = ReturnType<typeof useMessageVersions>
