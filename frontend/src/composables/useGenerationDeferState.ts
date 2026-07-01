import { ref } from 'vue'
import type { ChatMessage } from '../types/models'

/** 重写流式中断：local_rewrite 半截合并到该锚点气泡 */
export interface RewriteMergeContext {
  chatId: string
  anchorId: string
  anchorTs: string
  originalMessageId: string
}

/** 保存并发送：已更新用户消息后延后截断尾巴；中断时按尾巴形态保留半成品 */
export interface SaveSendDeferContext {
  chatId: string
  tailIdsToDeleteOnSuccess: string[]
  singleAssistantTailMergeId?: string | null
  mode: 'single' | 'group'
}

/**
 * 流式生成期间的延后删除 / 隐藏 / 重写合并上下文。
 * 提炼自 ChatPage.vue，供 omitMessageIds 与 UI 消息列表过滤共用。
 */
export function useGenerationDeferState() {
  /** 流式延后删除期间从列表隐藏的磁盘消息 id（与 omitMessageIds 对齐） */
  const streamHiddenMessageIds = ref<string[]>([])
  /** 流式成功后应从磁盘删除的消息 id（非 local_*） */
  const streamDeferDeleteIds = ref<string[]>([])
  const rewriteMergeCtx = ref<RewriteMergeContext | null>(null)
  const saveSendDeferCtx = ref<SaveSendDeferContext | null>(null)

  function clearVisibilityState() {
    streamHiddenMessageIds.value = []
    streamDeferDeleteIds.value = []
  }

  function clearAll() {
    clearVisibilityState()
    rewriteMergeCtx.value = null
    saveSendDeferCtx.value = null
  }

  function beginSaveSendDefer(ctx: SaveSendDeferContext) {
    saveSendDeferCtx.value = ctx
    streamDeferDeleteIds.value = ctx.tailIdsToDeleteOnSuccess
    streamHiddenMessageIds.value = [...ctx.tailIdsToDeleteOnSuccess]
  }

  function beginRewriteDefer(
    ctx: RewriteMergeContext,
    omitMessageIds: string[],
    tailDeleteIds: string[],
  ) {
    rewriteMergeCtx.value = ctx
    streamDeferDeleteIds.value = tailDeleteIds
    streamHiddenMessageIds.value = [...omitMessageIds]
  }

  function getSaveSendDeferForChat(chatId: string): SaveSendDeferContext | null {
    return saveSendDeferCtx.value?.chatId === chatId ? saveSendDeferCtx.value : null
  }

  /** 清理 save-send + 可见性，返回之前的快照（persistLocalStreamingMessages 用） */
  function clearSaveSendDeferForChat(chatId: string): SaveSendDeferContext | null {
    const ss = getSaveSendDeferForChat(chatId)
    if (!ss) return null
    saveSendDeferCtx.value = null
    clearVisibilityState()
    return ss
  }

  function clearRewriteAndVisibility() {
    rewriteMergeCtx.value = null
    clearVisibilityState()
  }

  /** 重写成功：取出待删尾部 id 并清 rewrite + 可见性 */
  function takeDeferDeleteIdsAfterRewrite(): string[] {
    const drop = [...streamDeferDeleteIds.value]
    rewriteMergeCtx.value = null
    clearVisibilityState()
    return drop
  }

  /** 重写流结束后处理延后删除（失败时仅恢复可见性，不删尾部） */
  async function finalizeRewriteAfterGeneration(
    chatId: string,
    hasError: boolean,
    finalizeTailDelete: (chatId: string, tailIds: string[]) => Promise<void>,
  ): Promise<void> {
    const ctx = rewriteMergeCtx.value
    if (!ctx || ctx.chatId !== chatId) return
    const drop = [...streamDeferDeleteIds.value]
    rewriteMergeCtx.value = null
    clearVisibilityState()
    if (!hasError && drop.length) {
      await finalizeTailDelete(chatId, drop)
    }
  }

  function filterVisibleMessages(messages: ChatMessage[]): ChatMessage[] {
    const hid = streamHiddenMessageIds.value
    if (!hid.length) return messages
    const hide = new Set(hid)
    return messages.filter((m) => !hide.has(m.id))
  }

  /** 生成流结束后处理 save-send 延后删除 */
  async function finalizeSaveSendAfterGeneration(
    chatId: string,
    hasError: boolean,
    finalizeTailDelete: (chatId: string, tailIds: string[]) => Promise<void>,
  ): Promise<boolean> {
    const ss = saveSendDeferCtx.value
    if (!ss || ss.chatId !== chatId) return false
    saveSendDeferCtx.value = null
    clearVisibilityState()
    if (!hasError && ss.tailIdsToDeleteOnSuccess.length) {
      await finalizeTailDelete(chatId, ss.tailIdsToDeleteOnSuccess)
    }
    return true
  }

  return {
    streamHiddenMessageIds,
    streamDeferDeleteIds,
    rewriteMergeCtx,
    saveSendDeferCtx,
    clearAll,
    clearVisibilityState,
    beginSaveSendDefer,
    beginRewriteDefer,
    getSaveSendDeferForChat,
    clearSaveSendDeferForChat,
    clearRewriteAndVisibility,
    takeDeferDeleteIdsAfterRewrite,
    finalizeRewriteAfterGeneration,
    filterVisibleMessages,
    finalizeSaveSendAfterGeneration,
  }
}
