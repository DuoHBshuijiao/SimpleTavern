/**
 * TTS 播放/下载 FAB 的拖动与贴边定位。
 * 与 useAssistantFabPosition 思路一致，独立 localStorage key。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { HEADER_LIFT_EASE, HEADER_LIFT_MS, MAIN_LAYOUT_TRANSITION_MS } from '../constants/chatHeaderMorph'

const STORAGE_KEY = 'st_chat_tts_playback_fab_v1'

export const TTS_FAB_BUTTON_SIZE = 48
export const TTS_FAB_GAP = 8
/** 容器高度 = 2 * 48 + 8 gap */
export const TTS_FAB_HEIGHT = TTS_FAB_BUTTON_SIZE * 2 + TTS_FAB_GAP

const RIGHT_GAP = 16
const LEFT_GAP = 8
const DRAG_THRESHOLD = 8
const EDGE_PAD = 8
const SNAP_MS = 320
const SNAP_EASE = 'cubic-bezier(0.34, 1.2, 0.64, 1)'
const SEPARATION_MS = 280
const SEPARATION_EASE = SNAP_EASE

interface Stored {
  side: 'left' | 'right'
  topPx: number
}

function loadStored(): Stored {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Stored
      if ((parsed.side === 'left' || parsed.side === 'right') && typeof parsed.topPx === 'number') {
        return parsed
      }
    }
  } catch { /* ignore */ }
  return { side: 'right', topPx: 80 }
}

function saveStored(data: Stored) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)) } catch { /* ignore */ }
}

function clampTop(top: number, minTop: number): number {
  const min = Math.max(minTop, EDGE_PAD)
  const max = Math.max(min, window.innerHeight - TTS_FAB_HEIGHT - EDGE_PAD)
  return Math.min(Math.max(min, top), max)
}

export function useTtsFabPosition(
  getContentLeft: () => number,
  getMinTop: () => number,
  options?: {
    onLayoutStable?: () => void
    onDragEnd?: () => void
    onSnapEnd?: () => void
    /** 与 ChatInput 输入栏下沉同相：侧栏收起且顶栏 lifting/full 时为 true */
    getInputSinkActive?: () => boolean
  },
) {
  const initial = loadStored()
  const side = ref<'left' | 'right'>(initial.side)
  const topPx = ref(clampTop(initial.topPx, getMinTop()))

  const isDragging = ref(false)
  const dragLeftPx = ref<number | null>(null)
  const dragTopPx = ref<number | null>(null)

  const isSnapping = ref(false)
  const snapAnimating = ref(false)
  const snapLeftPx = ref<number | null>(null)
  const snapTopPx = ref<number | null>(null)
  let snapEndTimer: ReturnType<typeof setTimeout> | null = null

  const isSeparationTopTransition = ref(false)
  let separationEndTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSeparationTimer: ReturnType<typeof setTimeout> | null = null

  const inputSinkActive = ref(false)
  /** 下沉用 transform 与回弹时长：与输入壳 lifting / 侧栏展开同频 */
  const sinkTransformTransition = ref('none')

  watch(
    () => options?.getInputSinkActive?.() ?? false,
    (active) => {
      inputSinkActive.value = active
      if (prefersReducedMotion()) {
        sinkTransformTransition.value = 'none'
        return
      }
      const dur = active ? HEADER_LIFT_MS : MAIN_LAYOUT_TRANSITION_MS
      const ease = active ? HEADER_LIFT_EASE : 'ease'
      sinkTransformTransition.value = `transform ${dur}ms ${ease}`
    },
    { immediate: true },
  )

  let pointerDown = false
  let hasDragged = false
  let grabOffsetX = 0
  let grabOffsetY = 0
  let dragStartX = 0
  let dragStartY = 0
  let activePointerId: number | null = null
  let capturedPointerId: number | null = null
  let suppressClick = false

  function persist(source: 'layout' | 'drag' = 'layout') {
    saveStored({ side: side.value, topPx: topPx.value })
    if (source === 'drag') options?.onDragEnd?.()
    else options?.onLayoutStable?.()
  }

  function prefersReducedMotion(): boolean {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  function cancelVerticalSeparationAnimation() {
    if (separationEndTimer != null) {
      clearTimeout(separationEndTimer)
      separationEndTimer = null
    }
    isSeparationTopTransition.value = false
  }

  function cancelPendingSeparation() {
    if (pendingSeparationTimer != null) {
      clearTimeout(pendingSeparationTimer)
      pendingSeparationTimer = null
    }
  }

  function cancelSnapAnimation() {
    if (snapEndTimer != null) { clearTimeout(snapEndTimer); snapEndTimer = null }
    isSnapping.value = false
    snapAnimating.value = false
    snapLeftPx.value = null
    snapTopPx.value = null
    cancelPendingSeparation()
  }

  function startSnapToEdge(fromLeft: number, fromTop: number, toLeft: number, toTop: number) {
    cancelSnapAnimation()
    const dist = Math.hypot(toLeft - fromLeft, toTop - fromTop)
    if (dist < 0.5 || prefersReducedMotion()) return
    isSnapping.value = true
    snapAnimating.value = false
    snapLeftPx.value = fromLeft
    snapTopPx.value = fromTop
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        snapAnimating.value = true
        snapLeftPx.value = toLeft
        snapTopPx.value = toTop
        snapEndTimer = setTimeout(() => {
          snapEndTimer = null
          cancelSnapAnimation()
          options?.onSnapEnd?.()
        }, SNAP_MS + 40)
      })
    })
  }

  function clampHorizontal(left: number): number {
    const max = Math.max(EDGE_PAD, window.innerWidth - TTS_FAB_BUTTON_SIZE - EDGE_PAD)
    return Math.min(Math.max(EDGE_PAD, left), max)
  }

  function sinkTransformForSide(s: 'left' | 'right'): string {
    return s === 'left' ? 'translateX(-100vw)' : 'translateX(100vw)'
  }

  const fabStyle = computed(() => {
    if (isDragging.value && dragLeftPx.value != null && dragTopPx.value != null) {
      return {
        position: 'fixed' as const,
        left: `${dragLeftPx.value}px`,
        top: `${dragTopPx.value}px`,
        right: 'auto' as const,
        zIndex: 50,
        touchAction: 'none' as const,
        transition: 'none',
        transform: 'none',
        pointerEvents: 'auto' as const,
      }
    }
    if (isSnapping.value && snapLeftPx.value != null && snapTopPx.value != null) {
      const trans = snapAnimating.value
        ? `left ${SNAP_MS}ms ${SNAP_EASE}, top ${SNAP_MS}ms ${SNAP_EASE}`
        : 'none'
      return {
        position: 'fixed' as const,
        left: `${snapLeftPx.value}px`,
        top: `${snapTopPx.value}px`,
        right: 'auto' as const,
        zIndex: 50,
        touchAction: 'none' as const,
        transition: trans,
        transform: 'none',
        pointerEvents: 'auto' as const,
      }
    }
    const top = clampTop(topPx.value, getMinTop())
    const topTrans = isSeparationTopTransition.value
      ? `top ${SEPARATION_MS}ms ${SEPARATION_EASE}`
      : 'none'
    const sinkMotion = inputSinkActive.value && !prefersReducedMotion()
    const sinkA11y = inputSinkActive.value && prefersReducedMotion()
    const sinkT = sinkTransformTransition.value
    const combinedTrans = [sinkT !== 'none' && sinkMotion ? sinkT : null, topTrans !== 'none' ? topTrans : null]
      .filter(Boolean)
      .join(', ') || 'none'
    const zWhenSink = 6
    if (side.value === 'left') {
      return {
        position: 'fixed' as const,
        left: `${getContentLeft() + LEFT_GAP}px`,
        top: `${top}px`,
        right: 'auto' as const,
        zIndex: sinkMotion || sinkA11y ? zWhenSink : 50,
        touchAction: 'none' as const,
        transition: combinedTrans,
        transform: sinkMotion ? sinkTransformForSide('left') : 'none',
        opacity: sinkA11y ? 0 : 1,
        pointerEvents: sinkMotion || sinkA11y ? ('none' as const) : ('auto' as const),
      }
    }
    return {
      position: 'fixed' as const,
      right: `${RIGHT_GAP}px`,
      top: `${top}px`,
      left: 'auto' as const,
      zIndex: sinkMotion || sinkA11y ? zWhenSink : 50,
      touchAction: 'none' as const,
      transition: combinedTrans,
      transform: sinkMotion ? sinkTransformForSide('right') : 'none',
      opacity: sinkA11y ? 0 : 1,
      pointerEvents: sinkMotion || sinkA11y ? ('none' as const) : ('auto' as const),
    }
  })

  /** 返回当前容器的矩形（用于碰撞检测）。 */
  function getRect(): DOMRect | null {
    const s = fabStyle.value
    let left: number
    if (s.left !== 'auto') {
      left = parseFloat(String(s.left))
    } else {
      left = window.innerWidth - TTS_FAB_BUTTON_SIZE - RIGHT_GAP
    }
    const top = parseFloat(String(s.top))
    return new DOMRect(left, top, TTS_FAB_BUTTON_SIZE, TTS_FAB_HEIGHT)
  }

  /** 由页面级碰撞分离调用，避免与助手 FAB 重叠 */
  function setTopPxFromSeparation(next: number) {
    const clamped = clampTop(next, getMinTop())
    if (Math.abs(clamped - topPx.value) < 0.5) return

    const applyNow = () => {
      if (prefersReducedMotion()) {
        cancelVerticalSeparationAnimation()
        topPx.value = clamped
        saveStored({ side: side.value, topPx: topPx.value })
        return
      }
      cancelVerticalSeparationAnimation()
      isSeparationTopTransition.value = true
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          topPx.value = clamped
          saveStored({ side: side.value, topPx: topPx.value })
          if (separationEndTimer != null) clearTimeout(separationEndTimer)
          separationEndTimer = setTimeout(() => {
            separationEndTimer = null
            isSeparationTopTransition.value = false
          }, SEPARATION_MS + 50)
        })
      })
    }

    if (isSnapping.value) {
      cancelPendingSeparation()
      pendingSeparationTimer = setTimeout(() => {
        pendingSeparationTimer = null
        setTopPxFromSeparation(clamped)
      }, SNAP_MS + 40)
      return
    }

    applyNow()
  }

  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0 || pointerDown) return
    cancelVerticalSeparationAnimation()
    cancelPendingSeparation()
    cancelSnapAnimation()
    const el = e.currentTarget as HTMLElement
    const rect = el.getBoundingClientRect()
    grabOffsetX = e.clientX - rect.left
    grabOffsetY = e.clientY - rect.top
    dragStartX = e.clientX
    dragStartY = e.clientY
    activePointerId = e.pointerId
    capturedPointerId = null
    pointerDown = true
    hasDragged = false
    dragLeftPx.value = null
    dragTopPx.value = null
    isDragging.value = false
  }

  function onPointerMove(e: PointerEvent) {
    if (!pointerDown || activePointerId !== e.pointerId) return
    const dx = e.clientX - dragStartX
    const dy = e.clientY - dragStartY
    if (!hasDragged && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      hasDragged = true
      isDragging.value = true
      const el = e.currentTarget as HTMLElement
      try {
        el.setPointerCapture(e.pointerId)
        capturedPointerId = e.pointerId
      } catch {
        capturedPointerId = null
      }
    }
    if (hasDragged) {
      e.preventDefault()
      dragLeftPx.value = clampHorizontal(e.clientX - grabOffsetX)
      dragTopPx.value = clampTop(e.clientY - grabOffsetY, getMinTop())
    }
  }

  function onPointerUp(e: PointerEvent) {
    if (!pointerDown || activePointerId !== e.pointerId) return
    const el = e.currentTarget as HTMLElement
    pointerDown = false
    activePointerId = null
    if (capturedPointerId === e.pointerId) {
      try { el.releasePointerCapture(e.pointerId) } catch { /* ignore */ }
    }
    capturedPointerId = null

    if (hasDragged) {
      const left = dragLeftPx.value ?? 0
      const top = clampTop(dragTopPx.value ?? topPx.value, getMinTop())
      const centerX = left + TTS_FAB_BUTTON_SIZE / 2
      const nextSide = centerX < window.innerWidth / 2 ? 'left' : 'right'
      const toLeft = nextSide === 'left'
        ? getContentLeft() + LEFT_GAP
        : window.innerWidth - TTS_FAB_BUTTON_SIZE - RIGHT_GAP
      side.value = nextSide
      topPx.value = top
      suppressClick = true
      persist('drag')
      startSnapToEdge(left, top, toLeft, top)
    }

    isDragging.value = false
    dragLeftPx.value = null
    dragTopPx.value = null
    hasDragged = false
  }

  function onPointerCancel(e: PointerEvent) {
    onPointerUp(e)
  }

  function onFabClick(e: MouseEvent): boolean {
    if (suppressClick) {
      e.preventDefault()
      e.stopPropagation()
      suppressClick = false
      return true
    }
    return false
  }

  function onResize() {
    cancelVerticalSeparationAnimation()
    cancelSnapAnimation()
    topPx.value = clampTop(topPx.value, getMinTop())
    persist()
  }

  watch(() => getMinTop(), () => {
    cancelVerticalSeparationAnimation()
    topPx.value = clampTop(topPx.value, getMinTop())
    persist()
  })

  let raf = 0
  function scheduleResize() {
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => { raf = 0; onResize() })
  }

  onMounted(() => { window.addEventListener('resize', scheduleResize, { passive: true }) })
  onUnmounted(() => {
    window.removeEventListener('resize', scheduleResize)
    if (raf) cancelAnimationFrame(raf)
    cancelVerticalSeparationAnimation()
    cancelPendingSeparation()
    cancelSnapAnimation()
  })

  return {
    fabStyle,
    getRect,
    setTopPxFromSeparation,
    side,
    topPx,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onFabClick,
  }
}
