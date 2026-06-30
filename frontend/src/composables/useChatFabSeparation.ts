import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { MAIN_LAYOUT_TRANSITION_MS } from '../constants/chatHeaderMorph'
import {
  computeAssistantNonOverlapTop,
  computeTtsNonOverlapTop,
  FAB_COLLISION_GAP_PX,
  rectsOverlap,
} from './useFabCollision'

export interface AssistantFabHost {
  getAssistantFabRect?: () => DOMRect | null | undefined
  setAssistantTopPx?: (top: number) => void
}

export interface TtsFabHost {
  getRect?: () => DOMRect | null | undefined
  setTtsTopPx?: (top: number) => void
}

export interface UseChatFabSeparationOptions {
  chatMainRef: Ref<HTMLElement | null>
  chatInputRef: Ref<AssistantFabHost | null>
  ttsPlaybackFabRef: Ref<TtsFabHost | null>
  chatAssistantFabMinTopPx: Ref<number>
  sidebarCollapsed: Ref<boolean>
  isNarrowPortrait: Ref<boolean>
  isTtsEnabled: () => boolean
}

/**
 * 主内容区左缘测量（供 FAB 贴边）与助手/TTS FAB 碰撞分离。
 * 提炼自 ChatPage.vue；布局过渡期间 rAF 同步左缘，避免与侧栏动画相位差。
 */
export function useChatFabSeparation(options: UseChatFabSeparationOptions) {
  const {
    chatMainRef,
    chatInputRef,
    ttsPlaybackFabRef,
    chatAssistantFabMinTopPx,
    sidebarCollapsed,
    isNarrowPortrait,
    isTtsEnabled,
  } = options

  const contentAreaLeftPx = ref(0)
  let contentAreaLeftRaf = 0
  let contentAreaLeftLayoutRaf = 0
  let contentAreaLeftSepDebounce: ReturnType<typeof setTimeout> | null = null

  function updateContentAreaLeft() {
    contentAreaLeftPx.value = chatMainRef.value?.getBoundingClientRect().left ?? 0
  }

  function scheduleContentAreaLeft() {
    if (contentAreaLeftRaf) cancelAnimationFrame(contentAreaLeftRaf)
    contentAreaLeftRaf = requestAnimationFrame(() => {
      contentAreaLeftRaf = 0
      updateContentAreaLeft()
    })
  }

  function cancelContentAreaLeftLayoutSync() {
    if (contentAreaLeftLayoutRaf) {
      cancelAnimationFrame(contentAreaLeftLayoutRaf)
      contentAreaLeftLayoutRaf = 0
    }
  }

  /**
   * 重叠时只移动「被锚定」的一侧：拖动助手则只挪助手，拖动 TTS 则只挪 TTS；
   * 布局类事件（挂载、resize、顶栏）默认只挪 TTS。
   */
  function runChatFabSeparation(anchor: 'assistant' | 'tts' | null = null) {
    if (!isTtsEnabled()) return
    nextTick(() => {
      const a = chatInputRef.value?.getAssistantFabRect?.()
      const t = ttsPlaybackFabRef.value?.getRect?.()
      if (!a || !t) return
      if (!rectsOverlap(a, t, FAB_COLLISION_GAP_PX)) return
      const minTop = chatAssistantFabMinTopPx.value

      if (anchor === 'assistant') {
        const newTop = computeAssistantNonOverlapTop(t, a, minTop)
        if (Math.abs(newTop - a.top) < 0.5) return
        chatInputRef.value?.setAssistantTopPx?.(newTop)
        return
      }
      const newTop = computeTtsNonOverlapTop(a, t, minTop)
      if (Math.abs(newTop - t.top) < 0.5) return
      ttsPlaybackFabRef.value?.setTtsTopPx?.(newTop)
    })
  }

  function syncContentAreaLeftDuringLayoutTransition() {
    cancelContentAreaLeftLayoutSync()
    const start = performance.now()
    const duration = MAIN_LAYOUT_TRANSITION_MS + 40
    const tick = () => {
      updateContentAreaLeft()
      if (performance.now() - start < duration) {
        contentAreaLeftLayoutRaf = requestAnimationFrame(() => {
          contentAreaLeftLayoutRaf = 0
          tick()
        })
      } else {
        updateContentAreaLeft()
        runChatFabSeparation()
      }
    }
    tick()
  }

  watch(sidebarCollapsed, () => {
    nextTick(() => {
      updateContentAreaLeft()
      runChatFabSeparation()
      syncContentAreaLeftDuringLayoutTransition()
    })
  })

  watch(isNarrowPortrait, () => {
    nextTick(() => scheduleContentAreaLeft())
  })

  watch(contentAreaLeftPx, () => {
    if (contentAreaLeftSepDebounce) clearTimeout(contentAreaLeftSepDebounce)
    contentAreaLeftSepDebounce = setTimeout(() => {
      contentAreaLeftSepDebounce = null
      runChatFabSeparation()
    }, 48)
  })

  watch(chatAssistantFabMinTopPx, () => runChatFabSeparation())

  watch(
    () => isTtsEnabled(),
    () => {
      nextTick(() => nextTick(runChatFabSeparation))
    },
  )

  onMounted(() => {
    window.addEventListener('resize', scheduleContentAreaLeft, { passive: true })
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', scheduleContentAreaLeft)
    if (contentAreaLeftRaf) cancelAnimationFrame(contentAreaLeftRaf)
    cancelContentAreaLeftLayoutSync()
    if (contentAreaLeftSepDebounce) clearTimeout(contentAreaLeftSepDebounce)
  })

  return {
    contentAreaLeftPx,
    updateContentAreaLeft,
    scheduleContentAreaLeft,
    runChatFabSeparation,
    syncContentAreaLeftDuringLayoutTransition,
  }
}
