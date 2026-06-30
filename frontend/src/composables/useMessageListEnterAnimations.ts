import { onBeforeUnmount, ref } from 'vue'

const USER_BUBBLE_ENTER_ANIM_MS = 480
const ASSISTANT_ROW_ENTER_ANIM_MS = 480

/**
 * MessageList 一次性入场动画状态：用户气泡与助手占位行。
 * 提炼自 ChatPage.vue，定时器在卸载时自动清理。
 */
export function useMessageListEnterAnimations() {
  const entrancingUserMessageId = ref<string | null>(null)
  let entrancingUserClearTimer: ReturnType<typeof setTimeout> | null = null

  const entrancingAssistantMessageId = ref<string | null>(null)
  let entrancingAssistantClearTimer: ReturnType<typeof setTimeout> | null = null

  function armUserMessageEnterAnimation(messageId: string) {
    entrancingUserMessageId.value = messageId
    if (entrancingUserClearTimer != null) clearTimeout(entrancingUserClearTimer)
    entrancingUserClearTimer = setTimeout(() => {
      entrancingUserClearTimer = null
      if (entrancingUserMessageId.value === messageId) entrancingUserMessageId.value = null
    }, USER_BUBBLE_ENTER_ANIM_MS)
  }

  function clearUserMessageEnterAnimation() {
    if (entrancingUserClearTimer != null) {
      clearTimeout(entrancingUserClearTimer)
      entrancingUserClearTimer = null
    }
    entrancingUserMessageId.value = null
  }

  function armAssistantRowEnterAnimation(messageId: string) {
    entrancingAssistantMessageId.value = messageId
    if (entrancingAssistantClearTimer != null) clearTimeout(entrancingAssistantClearTimer)
    entrancingAssistantClearTimer = setTimeout(() => {
      entrancingAssistantClearTimer = null
      if (entrancingAssistantMessageId.value === messageId) entrancingAssistantMessageId.value = null
    }, ASSISTANT_ROW_ENTER_ANIM_MS)
  }

  function clearAssistantRowEnterAnimation() {
    if (entrancingAssistantClearTimer != null) {
      clearTimeout(entrancingAssistantClearTimer)
      entrancingAssistantClearTimer = null
    }
    entrancingAssistantMessageId.value = null
  }

  function clearMessageListEnterAnimations() {
    clearUserMessageEnterAnimation()
    clearAssistantRowEnterAnimation()
  }

  onBeforeUnmount(() => {
    clearMessageListEnterAnimations()
  })

  return {
    entrancingUserMessageId,
    entrancingAssistantMessageId,
    armUserMessageEnterAnimation,
    clearUserMessageEnterAnimation,
    armAssistantRowEnterAnimation,
    clearAssistantRowEnterAnimation,
    clearMessageListEnterAnimations,
  }
}
