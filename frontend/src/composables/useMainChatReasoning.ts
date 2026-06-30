import { ref } from 'vue'
import type { Chat } from '../types/models'

export interface UseMainChatReasoningOptions {
  getActiveChat: () => Chat | null | undefined
}

/**
 * 主聊天思考链临时展示状态（不写持久化，刷新后消失）。
 * 提炼自 ChatPage.vue；持久化写入在 pushCurrentReasoningToBlocks / 生成路径中触发。
 */
export function useMainChatReasoning(options: UseMainChatReasoningOptions) {
  const { getActiveChat } = options

  const chatReasoningMessageId = ref<string | null>(null)
  const chatReasoningContent = ref('')
  const chatReasoningBlocks = ref<Array<{ messageId: string; content: string }>>([])
  const chatReasoningStreamActive = ref(false)
  const reasoningPhaseStartedAt = ref<number | null>(null)
  const chatReasoningElapsedSec = ref<number | null>(null)

  function markReasoningStreamPhaseStart() {
    reasoningPhaseStartedAt.value = Date.now()
    chatReasoningElapsedSec.value = null
  }

  function clearReasoningPhaseTiming() {
    reasoningPhaseStartedAt.value = null
    chatReasoningElapsedSec.value = null
  }

  /** 首条正文 delta：结束思考流式阶段并写入已用时长（秒） */
  function onAssistantContentDeltaStarted() {
    if (chatReasoningStreamActive.value && reasoningPhaseStartedAt.value != null) {
      chatReasoningElapsedSec.value =
        Math.round((Date.now() - reasoningPhaseStartedAt.value) / 100) / 10
    }
    chatReasoningStreamActive.value = false
  }

  /** 终止生成前：与首条正文 delta 一致，便于 ReasoningBubble 闭合过渡 */
  function finalizeReasoningElapsedBeforeStop() {
    if (chatReasoningStreamActive.value && reasoningPhaseStartedAt.value != null) {
      chatReasoningElapsedSec.value =
        Math.round((Date.now() - reasoningPhaseStartedAt.value) / 100) / 10
    }
  }

  function pushCurrentReasoningToBlocks(finalMessageId?: string | null, localAliasId?: string | null) {
    const primary = finalMessageId ?? chatReasoningMessageId.value
    const content = chatReasoningContent.value.trim()
    const ids = new Set<string>()
    if (primary) ids.add(primary)
    if (localAliasId && localAliasId !== primary) ids.add(localAliasId)

    const elapsed = chatReasoningElapsedSec.value
    const activeChat = getActiveChat()
    if (typeof elapsed === 'number' && Number.isFinite(elapsed) && activeChat && ids.size > 0) {
      for (const messageId of ids) {
        const msg = activeChat.messages.find((m) => m.id === messageId)
        if (msg && msg.role === 'assistant') {
          msg.reasoningDurationSec = elapsed
        }
      }
    }

    if (content && ids.size > 0 && activeChat) {
      for (const messageId of ids) {
        const msg = activeChat.messages.find((m) => m.id === messageId)
        if (msg && msg.role === 'assistant') {
          msg.reasoningContent = content
        }
      }
      let blocks = chatReasoningBlocks.value
      for (const messageId of ids) {
        blocks = [...blocks, { messageId, content }]
      }
      chatReasoningBlocks.value = blocks
    }
    chatReasoningContent.value = ''
    chatReasoningMessageId.value = null
    chatReasoningStreamActive.value = false
    clearReasoningPhaseTiming()
  }

  function getReasoningForMessageId(messageId: string): string {
    if (messageId === chatReasoningMessageId.value && chatReasoningContent.value) {
      return chatReasoningContent.value
    }
    const block = chatReasoningBlocks.value.find((b) => b.messageId === messageId)
    if (block?.content?.trim()) return block.content.trim()
    const msg = getActiveChat()?.messages.find((m) => m.id === messageId)
    return msg?.reasoningContent?.trim() ?? ''
  }

  function clearReasoningForChatSwitch() {
    chatReasoningBlocks.value = []
    chatReasoningContent.value = ''
    chatReasoningMessageId.value = null
    chatReasoningStreamActive.value = false
    clearReasoningPhaseTiming()
  }

  return {
    chatReasoningMessageId,
    chatReasoningContent,
    chatReasoningBlocks,
    chatReasoningStreamActive,
    chatReasoningElapsedSec,
    markReasoningStreamPhaseStart,
    clearReasoningPhaseTiming,
    onAssistantContentDeltaStarted,
    finalizeReasoningElapsedBeforeStop,
    pushCurrentReasoningToBlocks,
    getReasoningForMessageId,
    clearReasoningForChatSwitch,
  }
}

export type MainChatReasoningApi = ReturnType<typeof useMainChatReasoning>
