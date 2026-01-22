/**
 * useGroupChat - 群聊核心逻辑
 * 
 * 负责群聊的暂停/继续、轮次管理、插话等功能
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
  
  // 插话相关
  const showInterjectPanel = ref(false)     // 是否显示插话面板
  const isInterjecting = ref(false)         // 是否正在插话
  const interjectPanelManuallyHidden = ref(false)

  /**
   * 计算是否为纯 AI 模式
   */
  const effectivePureAiMode = computed(() => {
    const chatOverride = activeChat.value?.overrides?.pureAiMode
    if (chatOverride !== null && chatOverride !== undefined) return !!chatOverride
    return !!settings.settings?.pureAiMode
  })

  /**
   * 计算是否可以插话
   */
  const canInterject = computed(() => {
    return !!activeChat.value?.isGroup &&
      !isGenerating.value &&
      !isInterjecting.value &&
      !interjectPanelManuallyHidden.value &&
      (showInterjectPanel.value || effectivePureAiMode.value)
  })

  /**
   * 获取成员设置
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
   */
  function delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * 暂停群聊
   */
  function pauseGroupChat() {
    isPaused.value = true
  }

  /**
   * 重置群聊状态
   */
  function resetGroupState() {
    isPaused.value = false
    showContinueButton.value = false
    pendingMembers.value = []
    currentSpeakerIndex.value = -1
    interjectPanelManuallyHidden.value = false
  }

  /**
   * 设置暂停状态
   */
  function setPausedState(members: string[]) {
    pendingMembers.value = members
    showContinueButton.value = true
    isGenerating.value = false
    currentSpeakerIndex.value = -1
  }

  /**
   * 显示插话面板
   */
  function showInterject() {
    interjectPanelManuallyHidden.value = false
    showInterjectPanel.value = true
  }

  /**
   * 隐藏插话面板
   */
  function hideInterject() {
    showInterjectPanel.value = false
    interjectPanelManuallyHidden.value = true
  }

  /**
   * 获取群聊延迟时间
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
    showInterjectPanel,
    isInterjecting,
    interjectPanelManuallyHidden,
    
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
    hideInterject,
    getGroupDelay,
  }
}

export type UseGroupChat = ReturnType<typeof useGroupChat>
