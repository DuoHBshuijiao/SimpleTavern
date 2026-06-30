import { computed, onBeforeUnmount, ref } from 'vue'
import type { Chat, ForkLineageResponse, ForkSiblingSummary } from '../types/models'

export interface UseForkLineageOptions {
  /** 当前会话 getter */
  getActiveChat: () => Chat | null | undefined
  /** 拉取分叉血缘（通常为 chatsStore.fetchForkLineage） */
  fetchForkLineage: (chatId: string, signal: AbortSignal) => Promise<ForkLineageResponse>
}

/**
 * 会话分叉血缘（fork lineage）的加载、缓存、防抖与切会话清理。提炼自 ChatPage.vue，行为不变。
 *
 * 普通会话不主动拉 lineage；仅对带 `forkedFromChatId` 的会话在加载后防抖请求，并带 30s 缓存。
 */
export function useForkLineage(options: UseForkLineageOptions) {
  const { getActiveChat, fetchForkLineage } = options

  const forkLineage = ref<ForkLineageResponse | null>(null)
  const forkLineageLoading = ref(false)
  let forkLineageAbort: AbortController | null = null
  let forkLineageDebounceTimer: ReturnType<typeof setTimeout> | null = null
  const forkLineageCache = new Map<string, { value: ForkLineageResponse; expiresAt: number }>()
  const FORK_LINEAGE_CACHE_TTL_MS = 30_000

  const outgoingForksByMessageId = computed(() => {
    const map: Record<string, { count: number; chats: ForkSiblingSummary[] }> = {}
    for (const g of forkLineage.value?.outgoingForks ?? []) {
      map[g.messageId] = { count: g.count, chats: g.chats }
    }
    return map
  })

  async function refreshForkLineage(chatId: string) {
    forkLineageAbort?.abort()
    const ac = new AbortController()
    forkLineageAbort = ac
    forkLineageLoading.value = true
    try {
      const lineage = await fetchForkLineage(chatId, ac.signal)
      forkLineageCache.set(chatId, {
        value: lineage,
        expiresAt: Date.now() + FORK_LINEAGE_CACHE_TTL_MS,
      })
      forkLineage.value = lineage
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      forkLineage.value = null
    } finally {
      if (forkLineageAbort === ac) {
        forkLineageLoading.value = false
        forkLineageAbort = null
      }
    }
  }

  function cancelPendingForkLineage() {
    if (forkLineageDebounceTimer) {
      clearTimeout(forkLineageDebounceTimer)
      forkLineageDebounceTimer = null
    }
    forkLineageAbort?.abort()
    forkLineageAbort = null
    forkLineageLoading.value = false
  }

  function scheduleRefreshForkLineage(chatId: string, delayMs = 400) {
    if (forkLineageDebounceTimer) clearTimeout(forkLineageDebounceTimer)
    forkLineageDebounceTimer = setTimeout(() => {
      forkLineageDebounceTimer = null
      void refreshForkLineage(chatId)
    }, delayMs)
  }

  function syncForkLineageForLoadedChat(chatId: string) {
    const chat = getActiveChat()
    if (!chat || chat.id !== chatId) return
    cancelPendingForkLineage()

    const cached = forkLineageCache.get(chatId)
    if (cached && cached.expiresAt > Date.now()) {
      forkLineage.value = cached.value
      return
    }

    // 普通会话不主动拉 lineage，避免切换任意会话都产生慢请求。
    if (!chat.forkedFromChatId) {
      forkLineage.value = null
      return
    }

    scheduleRefreshForkLineage(chatId)
  }

  /** 切换会话时取消进行中的 lineage 请求并清空展示 */
  function resetForkLineage() {
    cancelPendingForkLineage()
    forkLineage.value = null
  }

  onBeforeUnmount(() => {
    cancelPendingForkLineage()
  })

  return {
    forkLineage,
    forkLineageLoading,
    outgoingForksByMessageId,
    refreshForkLineage,
    syncForkLineageForLoadedChat,
    resetForkLineage,
  }
}
