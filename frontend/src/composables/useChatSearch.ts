import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { apiGet } from '../api/http'
import type { Chat } from '../types/models'

export interface ChatSearchHit {
  messageId: string
  messageIndex: number
  snippet: string
  matchStart: number
  matchEnd: number
}

export function splitSearchSnippet(hit: ChatSearchHit): Array<{ text: string; match: boolean }> {
  const chars = Array.from(hit.snippet)
  return [
    { text: chars.slice(0, hit.matchStart).join(''), match: false },
    { text: chars.slice(hit.matchStart, hit.matchEnd).join(''), match: true },
    { text: chars.slice(hit.matchEnd).join(''), match: false },
  ].filter((part) => part.text)
}

export interface UseChatSearchOptions {
  /** 当前会话 getter；为空时搜索直接清空结果 */
  getActiveChat: () => Chat | null | undefined
  /** 跳转到指定消息（由页面负责滚动到 MessageList 对应项） */
  jumpToMessage: (messageId: string) => void
  /** 搜索输入框引用（由页面提供并绑定到模板 ref，打开搜索栏时用于聚焦/全选） */
  chatSearchInputRef: Ref<HTMLInputElement | null>
  /** 打开搜索栏前的副作用（如关闭顶栏“更多”菜单） */
  beforeOpen?: () => void
  beforeSearch?: () => Promise<void>
}

/**
 * 会话内搜索状态机：顶栏搜索栏的展开/收起动画时序、结果 chip 行的展开/收起、
 * 防抖查询、结果导航与跳转。提炼自 ChatPage.vue，行为保持不变。
 *
 * 依赖通过参数注入：`getActiveChat`（查询作用域）、`jumpToMessage`（滚动定位）、
 * `beforeOpen`（打开前副作用）。定时器在组件卸载时自动清理。
 */
export function useChatSearch(options: UseChatSearchOptions) {
  const { getActiveChat, jumpToMessage, chatSearchInputRef } = options

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
  const chatSearchError = ref('')
  /** 最近一次完成搜索的关键词，用来区分“还没搜”和“搜了没结果” */
  const chatSearchCompletedQuery = ref('')
  /** 命中数超过后端上限，计数要写成 300+ */
  const chatSearchTruncated = ref(false)
  let searchController: AbortController | null = null
  let chatSearchTimer: ReturnType<typeof setTimeout> | null = null
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
              if (chatSearchResults.value.length) chatSearchChipsGridOpen.value = true
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

  const chatSearchHitsForNav = chatSearchResults

  watch(chatSearchResults, () => syncChatSearchChipsRow(), { deep: true })

  function cancelSearch() {
    if (chatSearchTimer) clearTimeout(chatSearchTimer)
    chatSearchTimer = null
    searchController?.abort()
    searchController = null
    chatSearchLoading.value = false
  }

  function clearSearchResults() {
    chatSearchResults.value = []
    chatSearchCursor.value = -1
    chatSearchCompletedQuery.value = ''
    chatSearchTruncated.value = false
    chatSearchError.value = ''
    clearChatSearchChipsExpandState()
  }

  async function runChatSearch() {
    cancelSearch()
    const chatId = getActiveChat()?.id
    const q = chatSearchQuery.value.trim()
    if (!chatId || !q) {
      clearSearchResults()
      return
    }
    const controller = new AbortController()
    searchController = controller
    chatSearchError.value = ''
    chatSearchLoading.value = true
    try {
      await options.beforeSearch?.()
      if (controller.signal.aborted) return
      const res = await apiGet<{ query: string; total: number; hits: ChatSearchHit[]; truncated?: boolean }>(
        `/api/chats/${encodeURIComponent(chatId)}/search?q=${encodeURIComponent(q)}`,
        controller.signal,
      )
      if (searchController !== controller || getActiveChat()?.id !== chatId) return
      chatSearchResults.value = Array.isArray(res?.hits) ? res.hits : []
      chatSearchCursor.value = -1
      chatSearchCompletedQuery.value = q
      chatSearchTruncated.value = res?.truncated === true
    } catch (error) {
      if (searchController !== controller) return
      clearSearchResults()
      chatSearchError.value = error instanceof Error ? error.message : String(error)
    } finally {
      if (searchController === controller) {
        searchController = null
        chatSearchLoading.value = false
      }
    }
  }

  async function handleChatSearchEnter(backward = false) {
    const q = chatSearchQuery.value.trim()
    const chatId = getActiveChat()?.id
    if (!q || !chatId) return
    if (q !== chatSearchCompletedQuery.value) await runChatSearch()
    if (getActiveChat()?.id !== chatId || chatSearchCompletedQuery.value !== q) return
    if (backward) goToPrevSearchResult()
    else goToNextSearchResult()
  }

  function goToNextSearchResult() {
    const list = chatSearchHitsForNav.value
    const total = list.length
    if (!total) return
    if (chatSearchCursor.value < 0) {
      chatSearchCursor.value = 0
    } else {
      chatSearchCursor.value = (chatSearchCursor.value + 1) % total
    }
    jumpToMessage(list[chatSearchCursor.value]!.messageId)
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
    jumpToMessage(list[chatSearchCursor.value]!.messageId)
  }

  function jumpToSearchResult(idx: number) {
    const hit = chatSearchHitsForNav.value[idx]
    if (!hit) return
    chatSearchCursor.value = idx
    jumpToMessage(hit.messageId)
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
    cancelSearch()
    chatSearchInputRef.value?.blur()
    chatSearchQuery.value = ''
    clearSearchResults()
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

  function scheduleSearch() {
    cancelSearch()
    clearSearchResults()
    if (!showChatSearch.value || !chatSearchQuery.value.trim()) return
    chatSearchTimer = setTimeout(() => { void runChatSearch() }, 180)
  }

  watch(chatSearchQuery, scheduleSearch, { flush: 'sync' })
  watch(() => getActiveChat()?.id, () => resetChatSearchForChatSwitch(), { flush: 'sync' })
  watch(() => showChatSearch.value && chatSearchQuery.value.trim()
    ? getActiveChat()?.messages.map(({ id, content }) => [id, content])
    : undefined,
  (current, previous) => {
    if (!previous || !current) return
    if (current.length !== previous.length || current.some(([id, content], index) =>
      previous[index]?.[0] !== id || previous[index]?.[1] !== content)) scheduleSearch()
  })

  /** 切换会话时自动关闭搜索面板并重置搜索状态 */
  function resetChatSearchForChatSwitch() {
    cancelSearch()
    clearChatSearchAnimTimers()
    holdSearchChipUntilSearchPanelClosed.value = false
    chatSearchExpandOpen.value = false
    chatSearchContentRevealed.value = false
    showChatSearch.value = false
    chatSearchQuery.value = ''
    clearSearchResults()
  }

  onBeforeUnmount(() => {
    cancelSearch()
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
    chatSearchError,
    chatSearchCompletedQuery,
    chatSearchTruncated,
    chatSearchResults,
    chatSearchCursor,
    chatSearchChipsGridOpen,
    chatSearchChipsCollapsing,
    chatSearchChipsDisplayHits,
    chatSearchHitsForNav,
    runChatSearch,
    handleChatSearchEnter,
    goToNextSearchResult,
    goToPrevSearchResult,
    jumpToSearchResult,
    openChatSearchBar,
    closeChatSearchBar,
    resetChatSearchForChatSwitch,
  }
}
