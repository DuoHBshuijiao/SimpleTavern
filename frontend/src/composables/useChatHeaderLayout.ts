import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type CSSProperties, type Ref } from 'vue'
import {
  HEADER_EXPAND_MS,
  HEADER_LIFT_EASE,
  HEADER_LIFT_MS,
  HEADER_SQUEEZE_EASE,
  HEADER_SQUEEZE_MS,
  type HeaderMorphPhase,
} from '../constants/chatHeaderMorph'

export type ChatHeaderFixedStyle = CSSProperties & {
  position: 'fixed'
  left: string
  right: string
  top: string
  zIndex: number
  borderRadius: string
  transition: string
}

export interface UseChatHeaderLayoutOptions {
  sidebarCollapsed: Ref<boolean>
  isNarrowPortrait: Ref<boolean>
  isTtsEnabled: () => boolean
}

/**
 * 顶栏 morph（inset → lifting → full）、固定定位样式、高度测量与 TTS/Agent 顶栏控件显隐。
 * 提炼自 ChatPage.vue；`headerMorphPhase` 亦供 WebGPU 背景与 ChatInput 同步。
 */
export function useChatHeaderLayout(options: UseChatHeaderLayoutOptions) {
  const { sidebarCollapsed, isNarrowPortrait, isTtsEnabled } = options

  const headerMorphPhase = ref<HeaderMorphPhase>('inset')
  const headerEasingMs = ref(320)

  let headerCompactDelayTimer: ReturnType<typeof setTimeout> | null = null
  let headerLiftChainTimer: ReturnType<typeof setTimeout> | null = null

  function clearHeaderMorphTimers() {
    if (headerCompactDelayTimer != null) {
      clearTimeout(headerCompactDelayTimer)
      headerCompactDelayTimer = null
    }
    if (headerLiftChainTimer != null) {
      clearTimeout(headerLiftChainTimer)
      headerLiftChainTimer = null
    }
  }

  watch(sidebarCollapsed, (collapsed) => {
    clearHeaderMorphTimers()
    if (!collapsed) {
      headerEasingMs.value = HEADER_EXPAND_MS
      headerMorphPhase.value = 'inset'
      window.setTimeout(() => {
        headerEasingMs.value = 320
      }, 220)
      return
    }
    headerMorphPhase.value = 'inset'
    headerCompactDelayTimer = window.setTimeout(() => {
      headerMorphPhase.value = 'lifting'
      headerCompactDelayTimer = null
      headerLiftChainTimer = window.setTimeout(() => {
        headerMorphPhase.value = 'full'
        headerLiftChainTimer = null
      }, HEADER_LIFT_MS)
    }, 1000)
  })

  const chatHeaderStyle: ComputedRef<ChatHeaderFixedStyle> = computed(() => {
    const phase = headerMorphPhase.value
    const collapsed = sidebarCollapsed.value
    const ms = headerEasingMs.value
    const insetLeft =
      collapsed || isNarrowPortrait.value ? 'calc(1rem + 0.75rem)' : 'calc(21rem + 0.75rem)'
    const insetRight = '0.75rem'
    const insetTop = '0.75rem'
    const radiusOpen = 'var(--radius-2xl)'

    if (phase === 'full') {
      return {
        position: 'fixed',
        left: '0',
        right: '0',
        top: '0',
        zIndex: 10,
        borderRadius: '0',
        transition: `left ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}, right ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}, border-radius ${HEADER_SQUEEZE_MS}ms ${HEADER_SQUEEZE_EASE}`,
      }
    }

    if (phase === 'lifting') {
      return {
        position: 'fixed',
        left: insetLeft,
        right: insetRight,
        top: '0',
        zIndex: 10,
        borderRadius: radiusOpen,
        transition: `top ${HEADER_LIFT_MS}ms ${HEADER_LIFT_EASE}`,
      }
    }

    const transition = `left ${ms}ms ease, right ${ms}ms ease, top ${ms}ms ease, border-radius ${ms}ms ease`
    return {
      position: 'fixed',
      left: insetLeft,
      right: insetRight,
      top: insetTop,
      zIndex: 10,
      borderRadius: radiusOpen,
      transition,
    }
  })

  const chatHeaderRef = ref<HTMLElement | null>(null)
  const chatHeaderHeightPx = ref(72)
  const chatAssistantFabMinTopPx = ref(0)
  let chatHeaderResizeObserver: ResizeObserver | null = null

  const ASSISTANT_FAB_HEADER_GAP_PX = 8

  watch(
    () => chatHeaderRef.value,
    (el) => {
      chatHeaderResizeObserver?.disconnect()
      chatHeaderResizeObserver = null
      if (!el) return
      const apply = () => {
        const rect = el.getBoundingClientRect()
        const h = rect.height
        if (h > 0) chatHeaderHeightPx.value = Math.round(h * 100) / 100
        chatAssistantFabMinTopPx.value =
          Math.round((rect.bottom + ASSISTANT_FAB_HEADER_GAP_PX) * 100) / 100
      }
      apply()
      chatHeaderResizeObserver = new ResizeObserver(() => {
        apply()
      })
      chatHeaderResizeObserver.observe(el)
    },
    { flush: 'post' },
  )

  const ttsInputSinkActive = computed(
    () =>
      sidebarCollapsed.value &&
      (headerMorphPhase.value === 'lifting' || headerMorphPhase.value === 'full'),
  )

  const ttsTopBarControlsVisible = ref(false)
  let ttsTopBarRevealTimer: ReturnType<typeof setTimeout> | null = null

  function clearTtsTopBarRevealTimer() {
    if (ttsTopBarRevealTimer != null) {
      clearTimeout(ttsTopBarRevealTimer)
      ttsTopBarRevealTimer = null
    }
  }

  watch(
    () => [sidebarCollapsed.value, headerMorphPhase.value, isTtsEnabled()] as const,
    () => {
      clearTtsTopBarRevealTimer()
      if (!sidebarCollapsed.value || !isTtsEnabled()) {
        ttsTopBarControlsVisible.value = false
        return
      }
      if (headerMorphPhase.value === 'full') {
        ttsTopBarRevealTimer = setTimeout(() => {
          ttsTopBarControlsVisible.value = true
          ttsTopBarRevealTimer = null
        }, HEADER_SQUEEZE_MS + 40)
      } else {
        ttsTopBarControlsVisible.value = false
      }
    },
    { flush: 'post' },
  )

  const agentTopBarControlsVisible = ref(false)
  let agentTopBarRevealTimer: ReturnType<typeof setTimeout> | null = null

  function clearAgentTopBarRevealTimer() {
    if (agentTopBarRevealTimer != null) {
      clearTimeout(agentTopBarRevealTimer)
      agentTopBarRevealTimer = null
    }
  }

  watch(
    () => [sidebarCollapsed.value, headerMorphPhase.value] as const,
    () => {
      clearAgentTopBarRevealTimer()
      if (!sidebarCollapsed.value) {
        agentTopBarControlsVisible.value = false
        return
      }
      if (headerMorphPhase.value === 'full') {
        agentTopBarRevealTimer = setTimeout(() => {
          agentTopBarControlsVisible.value = true
          agentTopBarRevealTimer = null
        }, HEADER_SQUEEZE_MS + 40)
      } else {
        agentTopBarControlsVisible.value = false
      }
    },
    { flush: 'post' },
  )

  onBeforeUnmount(() => {
    clearHeaderMorphTimers()
    clearTtsTopBarRevealTimer()
    clearAgentTopBarRevealTimer()
    chatHeaderResizeObserver?.disconnect()
    chatHeaderResizeObserver = null
  })

  return {
    headerMorphPhase,
    headerEasingMs,
    chatHeaderStyle,
    chatHeaderRef,
    chatHeaderHeightPx,
    chatAssistantFabMinTopPx,
    ttsInputSinkActive,
    ttsTopBarControlsVisible,
    agentTopBarControlsVisible,
  }
}
