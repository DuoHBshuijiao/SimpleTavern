import { computed, nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { apiGet } from '../api/http'
import type { Chat } from '../types/models'

export interface ChatSearchHit {
  messageId: string
  messageIndex: number
  snippet: string
}

export interface UseChatSearchOptions {
  /** 当前会话 getter；为空时搜索直接清空结果 */
  getActiveChat: () => Chat | null | undefined
  /** 跳转到指定消息序号（由页面负责滚动到 MessageList 对应项） */
  jumpToMessageIndex: (index: number) => void
  /** 搜索输入框引用（由页面提供并绑定到模板 ref，打开搜索栏时用于聚焦/全选） */
  chatSearchInputRef: Ref<HTMLInputElement | null>
  /** 打开搜索栏前的副作用（如关闭顶栏“更多”菜单） */
  beforeOpen?: () => void
}

/**
 * 会话内搜索状态机：顶栏搜索栏的展开/收起动画时序、结果 chip 行的展开/收起、
 * 防抖查询、结果导航与跳转。提炼自 ChatPage.vue，行为保持不变。
 *
 * 依赖通过参数注入：`getActiveChat`（查询作用域）、`jumpToMessageIndex`（滚动定位）、
 * `beforeOpen`（打开前副作用）。定时器在组件卸载时自动清理。
 */
export function useChatSearch(options: UseChatSearchOptions) {
  const { getActiveChat, jumpToMessageIndex, chatSearchInputRef } = options

  const showChatSearch = ref(false)
  /** 关闭搜索栏时先跑完面板离场动画再显示「搜索」chip，避免与收起动画抢布局造成顿挫 */
  const holdSearchChipUntilSearchPanelClosed = ref(false)
  /** 顶栏搜索区向下拓展（grid 0fr→1fr） */
  const chatSearchExpandOpen = ref(false)
  /** 拓展占位完成后「带出」搜索 UI（opacity / translate） */
  const chatSearchContentRevealed = ref(false)

  const SEARCH_OPEN_EXPAND_MS = 320
  const SEARCH_REVEAL_DELAY_MS = 500
  const SEARCH_CLOSE_CONTENT_MS = 280
  const SEARCH_EXPAND_COLLAPSE_MS = 320

  let chatSearchOpenRevealTimer: ReturnType<typeof setTimeout> | null = null
  let chatSearchCloseTimers: ReturnType<typeof setTimeout>[] = []

  function prefersReducedMotion(): boolean {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  /** 仅清理搜索面板展开/收起与 reveal 的定时器，不碰 chip 状态（关闭动画需与 chip 同场） */
  function clearChatSearchPanelAnimTimers() {
    if (chatSearchOpenRevealTimer != null) {
      clearTimeout(chatSearchOpenRevealTimer)
      chatSearchOpenRevealTimer = null
    }
    chatSearchCloseTimers.forEach(clearTimeout)
    chatSearchCloseTimers = []
  }

  /** 面板定时器 + chip 展开状态，用于切会话、卸载等完整重置 */
  function clearChatSearchAnimTimers() {
    clearChatSearchPanelAnimTimers()
    clearChatSearchChipsExpandState()
  }
  const chatSearchQuery = ref('')
  const chatSearchLoading = ref(false)
  const chatSearchResults = ref<ChatSearchHit[]>([])
  /** 当前高亮的搜索结果 chip；-1 表示未选中（搜索成功后不再默认选中首条） */
  const chatSearchCursor = ref(-1)
  /** chip 行：grid 展开；清空结果时先收起再延迟清 DOM，以便高度过渡 */
  const chatSearchChipsGridOpen = ref(false)
  const chatSearchChipsCollapsing = ref(false)
  const chatSearchChipsDisplayHits = ref<ChatSearchHit[]>([])
  let chatSearchChipsClearTimer: ReturnType<typeof setTimeout> | null = null

  function clearChatSearchChipsExpandState() {
    if (chatSearchChipsClearTimer != null) {
      clearTimeout(chatSearchChipsClearTimer)
      chatSearchChipsClearTimer = null
    }
    chatSearchChipsDisplayHits.value = []
    chatSearchChipsGridOpen.value = false
    chatSearchChipsCollapsing.value = false
  }

  function syncChatSearchChipsRow(syncOptions?: { forceExpandAnimation?: boolean }) {
    const hits = chatSearchResults.value
    if (hits.length > 0) {
      if (chatSearchChipsClearTimer != null) {
        clearTimeout(chatSearchChipsClearTimer)
        chatSearchChipsClearTimer = null
      }
      chatSearchChipsCollapsing.value = false
      const wasEmpty = chatSearchChipsDisplayHits.value.length === 0
      chatSearchChipsDisplayHits.value = hits.map((h) => ({ ...h }))
      const shouldAnimateExpand =
        !prefersReducedMotion() && (syncOptions?.forceExpandAnimation === true || wasEmpty)
      if (shouldAnimateExpand) {
        chatSearchChipsGridOpen.value = false
        nextTick(() => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              chatSearchChipsGridOpen.value = true
            })
          })
        })
      } else {
        chatSearchChipsGridOpen.value = true
      }
    } else {
      if (chatSearchChipsDisplayHits.value.length === 0) {
        chatSearchChipsGridOpen.value = false
        return
      }
      if (prefersReducedMotion()) {
        clearChatSearchChipsExpandState()
        return
      }
      chatSearchChipsCollapsing.value = true
      chatSearchChipsGridOpen.value = false
      if (chatSearchChipsClearTimer != null) {
        clearTimeout(chatSearchChipsClearTimer)
        chatSearchChipsClearTimer = null
      }
      chatSearchChipsClearTimer = setTimeout(() => {
        chatSearchChipsDisplayHits.value = []
        chatSearchChipsCollapsing.value = false
        chatSearchChipsClearTimer = null
      }, SEARCH_CLOSE_CONTENT_MS)
    }
  }

  const chatSearchHitsForNav = computed(() =>
    chatSearchResults.value.length > 0 ? chatSearchResults.value : chatSearchChipsDisplayHits.value
  )

  watch(chatSearchResults, () => syncChatSearchChipsRow(), { deep: true })

  async function runChatSearch() {
    const chat = getActiveChat()
    const q = chatSearchQuery.value.trim()
    if (!chat || !q) {
      chatSearchResults.value = []
      chatSearchCursor.value = -1
      return
    }
    chatSearchLoading.value = true
    try {
      const res = await apiGet<{ query: string; total: number; hits: ChatSearchHit[] }>(
        `/api/chats/${encodeURIComponent(chat.id)}/search?q=${encodeURIComponent(q)}`
      )
      chatSearchResults.value = Array.isArray(res?.hits) ? res.hits : []
      chatSearchCursor.value = -1
    } finally {
      chatSearchLoading.value = false
    }
  }

  let chatSearchTimer: ReturnType<typeof setTimeout> | null = null

  function goToNextSearchResult() {
    const list = chatSearchHitsForNav.value
    const total = list.length
    if (!total) return
    if (chatSearchCursor.value < 0) {
      chatSearchCursor.value = 0
    } else {
      chatSearchCursor.value = (chatSearchCursor.value + 1) % total
    }
    jumpToMessageIndex(list[chatSearchCursor.value]!.messageIndex)
  }

  function goToPrevSearchResult() {
    const list = chatSearchHitsForNav.value
    const total = list.length
    if (!total) return
    if (chatSearchCursor.value < 0) {
      chatSearchCursor.value = total - 1
    } else {
      chatSearchCursor.value = (chatSearchCursor.value - 1 + total) % total
    }
    jumpToMessageIndex(list[chatSearchCursor.value]!.messageIndex)
  }

  function jumpToSearchResult(idx: number) {
    const hit = chatSearchHitsForNav.value[idx]
    if (!hit) return
    chatSearchCursor.value = idx
    jumpToMessageIndex(hit.messageIndex)
  }

  function openChatSearchBar() {
    holdSearchChipUntilSearchPanelClosed.value = false
    options.beforeOpen?.()
    clearChatSearchPanelAnimTimers()
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    showChatSearch.value = true
    nextTick(() => {
      if (prefersReducedMotion()) {
        chatSearchExpandOpen.value = true
        chatSearchContentRevealed.value = true
        nextTick(() => {
          if (chatSearchResults.value.length > 0) {
            syncChatSearchChipsRow({ forceExpandAnimation: true })
          }
          chatSearchInputRef.value?.focus()
          chatSearchInputRef.value?.select()
        })
        return
      }
      chatSearchExpandOpen.value = true
      chatSearchOpenRevealTimer = window.setTimeout(() => {
        chatSearchContentRevealed.value = true
        chatSearchOpenRevealTimer = null
        nextTick(() => {
          if (chatSearchResults.value.length > 0) {
            syncChatSearchChipsRow({ forceExpandAnimation: true })
          }
          chatSearchInputRef.value?.focus()
          chatSearchInputRef.value?.select()
        })
      }, SEARCH_REVEAL_DELAY_MS)
    })
  }

  function closeChatSearchBar() {
    if (!showChatSearch.value) return
    clearChatSearchPanelAnimTimers()
    holdSearchChipUntilSearchPanelClosed.value = true
    if (prefersReducedMotion()) {
      chatSearchExpandOpen.value = false
      chatSearchContentRevealed.value = false
      showChatSearch.value = false
      holdSearchChipUntilSearchPanelClosed.value = false
      return
    }
    chatSearchContentRevealed.value = false
    const half = SEARCH_CLOSE_CONTENT_MS / 2
    const tExpand = window.setTimeout(() => {
      chatSearchExpandOpen.value = false
    }, half)
    const totalEnd = Math.max(SEARCH_CLOSE_CONTENT_MS, half + SEARCH_EXPAND_COLLAPSE_MS)
    const tDone = window.setTimeout(() => {
      showChatSearch.value = false
      holdSearchChipUntilSearchPanelClosed.value = false
      chatSearchExpandOpen.value = false
      chatSearchContentRevealed.value = false
      chatSearchCloseTimers = []
    }, totalEnd)
    chatSearchCloseTimers = [tExpand, tDone]
  }

  watch(chatSearchQuery, () => {
    if (!showChatSearch.value || !chatSearchContentRevealed.value) return
    if (chatSearchTimer) clearTimeout(chatSearchTimer)
    chatSearchTimer = setTimeout(() => {
      void runChatSearch()
    }, 180)
  })

  /** 切换会话时自动关闭搜索面板并重置搜索状态 */
  function resetChatSearchForChatSwitch() {
    clearChatSearchAnimTimers()
    holdSearchChipUntilSearchPanelClosed.value = false
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    showChatSearch.value = false
    chatSearchQuery.value = ''
    chatSearchResults.value = []
    chatSearchCursor.value = -1
  }

  onBeforeUnmount(() => {
    if (chatSearchTimer) clearTimeout(chatSearchTimer)
    clearChatSearchAnimTimers()
  })

  return {
    showChatSearch,
    holdSearchChipUntilSearchPanelClosed,
    chatSearchExpandOpen,
    chatSearchContentRevealed,
    SEARCH_OPEN_EXPAND_MS,
    SEARCH_CLOSE_CONTENT_MS,
    SEARCH_EXPAND_COLLAPSE_MS,
    chatSearchQuery,
    chatSearchLoading,
    chatSearchResults,
    chatSearchCursor,
    chatSearchChipsGridOpen,
    chatSearchChipsCollapsing,
    chatSearchChipsDisplayHits,
    chatSearchHitsForNav,
    runChatSearch,
    goToNextSearchResult,
    goToPrevSearchResult,
    jumpToSearchResult,
    openChatSearchBar,
    closeChatSearchBar,
    resetChatSearchForChatSwitch,
  }
}
