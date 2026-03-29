/**
 * useGroupChat - 群聊核心逻辑Composable
 *
 * 负责群聊的暂停/继续、轮次管理、插话等功能。
 *
 * 主要功能：
 *    - 暂停/继续：控制群聊的暂停和继续
 *    - 成员筛选：根据概率筛选参与本轮对话的成员
 *    - 插话：是否可触发单次回应（由 canInterject 计算）
 *    - 状态管理：管理当前发言者、待发言成员等状态
 *
 * 主要函数：
 *    - getMemberSettings: 获取成员设置
 *    - filterMembersByProbability: 根据概率筛选成员
 *    - delay: 延迟函数
 *    - pauseGroupChat: 暂停群聊
 *    - resetGroupState: 重置群聊状态
 *    - setPausedState: 设置暂停状态
 *    - showInterject: 兼容占位（插话条常驻后无状态可切换）
 *    - getGroupDelay: 获取群聊延迟时间
 *
 * 计算属性：
 *    - effectivePureAiMode: 计算是否为纯AI模式
 *    - canInterject: 计算是否可以插话
 *
 * 文件关系：
 *    - 被导入：被composables/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和computed、types/models.ts的类型
 *    - 依赖：依赖vue、stores/settings.ts（通过参数传入）
 *    - 位置：Composables层，提供群聊逻辑
 */
import { ref, computed } from 'vue'
import type { Ref } from 'vue'
import type { Chat, GroupMemberSettings } from '../types/models'

export interface GroupChatDeps {
  activeChat: Ref<Chat | null>
  isGenerating: Ref<boolean>
  settings: {
    settings: {
      pureAiMode?: boolean
    } | null
  }
}

export function useGroupChat(deps: GroupChatDeps) {
  const { activeChat, isGenerating, settings } = deps

  // 群聊暂停/继续相关状态
  const isPaused = ref(false)
  const pendingMembers = ref<string[]>([])  // 暂停时剩余待发言的成员
  const showContinueButton = ref(false)     // 是否显示"继续轮次"按钮
  
  // 当前正在发言的角色索引（群聊用）
  const currentSpeakerIndex = ref<number>(-1)
  
  // 插话（单次回应）进行中
  const isInterjecting = ref(false)

  /**
   * 计算是否为纯AI模式
   *
   * 优先使用聊天会话的覆盖设置，如果没有则使用全局设置。
   *
   * @returns {boolean} 是否为纯AI模式
   */
  const effectivePureAiMode = computed(() => {
    const chatOverride = activeChat.value?.overrides?.pureAiMode
    if (chatOverride !== null && chatOverride !== undefined) return !!chatOverride
    return !!settings.settings?.pureAiMode
  })

  /**
   * 是否可触发单次回应（点头像）：群聊且当前无整轮生成、无单次回应进行中。
   */
  const canInterject = computed(() => {
    return !!activeChat.value?.isGroup &&
      !isGenerating.value &&
      !isInterjecting.value
  })

  /**
   * 获取成员设置
   *
   * 获取群聊中指定成员的个性化设置，如果不存在则返回默认设置。
   *
   * @param {string} memberId - 成员角色ID
   * @returns {GroupMemberSettings} 成员设置（来自types/models.ts）
   */
  function getMemberSettings(memberId: string): GroupMemberSettings {
    return activeChat.value?.memberSettings?.[memberId] ?? {
      model: null,
      presetId: null,
      temperature: null,
      top_p: null,
      probability: 1.0,
      includePersonality: true,
      includeScenario: true,
    }
  }

  /**
   * 根据概率筛选本轮参与的成员
   *
   * 根据每个成员的参与概率（probability）随机决定是否参与本轮对话。
   * 如果所有成员都被跳过，则至少随机选择一个成员参与。
   *
   * @param {string[]} allMemberIds - 所有成员ID列表
   * @returns {string[]} 筛选后的成员ID列表
   */
  function filterMembersByProbability(allMemberIds: string[]): string[] {
    const memberIds = allMemberIds.filter(memberId => {
      const memberSettings = activeChat.value?.memberSettings?.[memberId]
      const probability = memberSettings?.probability ?? 1.0
      return Math.random() < probability
    })
    
    // 如果所有成员都被跳过，至少保留一个（随机选择）
    if (memberIds.length === 0 && allMemberIds.length > 0) {
      const randomIdx = Math.floor(Math.random() * allMemberIds.length)
      memberIds.push(allMemberIds[randomIdx]!)
    }
    
    return memberIds
  }

  /**
   * 延迟函数
   *
   * 创建一个延迟指定毫秒数的Promise，用于群聊中角色发言之间的延迟。
   *
   * @param {number} ms - 延迟毫秒数
   * @returns {Promise<void>} 延迟完成的Promise
   */
  function delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * 暂停群聊
   *
   * 设置暂停状态，停止当前轮次的生成。
   */
  function pauseGroupChat() {
    isPaused.value = true
  }

  /**
   * 重置群聊状态
   *
   * 重置所有群聊相关状态，包括暂停状态、待发言成员、当前发言者等。
   */
  function resetGroupState() {
    isPaused.value = false
    showContinueButton.value = false
    pendingMembers.value = []
    currentSpeakerIndex.value = -1
  }

  /**
   * 设置暂停状态
   *
   * 当群聊被暂停时，保存剩余待发言的成员列表，显示继续按钮。
   *
   * @param {string[]} members - 剩余待发言的成员ID列表
   */
  function setPausedState(members: string[]) {
    pendingMembers.value = members
    showContinueButton.value = true
    isGenerating.value = false
    currentSpeakerIndex.value = -1
  }

  /** 兼容旧调用点：插话条常驻后无需切换状态 */
  function showInterject() {}

  /**
   * 获取群聊延迟时间
   *
   * 获取群聊中角色发言之间的延迟时间（毫秒），如果未设置则返回默认值1500。
   *
   * @returns {number} 延迟时间（毫秒）
   */
  function getGroupDelay(): number {
    return activeChat.value?.groupDelay || 1500
  }

  return {
    // 状态
    isPaused,
    pendingMembers,
    showContinueButton,
    currentSpeakerIndex,
    isInterjecting,
    
    // 计算属性
    effectivePureAiMode,
    canInterject,
    
    // 方法
    getMemberSettings,
    filterMembersByProbability,
    delay,
    pauseGroupChat,
    resetGroupState,
    setPausedState,
    showInterject,
    getGroupDelay,
  }
}

export type UseGroupChat = ReturnType<typeof useGroupChat>
