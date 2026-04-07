/**
 * 聊天页「助手」浮动按钮：拖动、左右贴边、垂直位置 localStorage 持久化。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const STORAGE_KEY = 'st_chat_assistant_fab_v1'

export const ASSISTANT_FAB_SIZE = 48
const RIGHT_GAP = 16
const LEFT_GAP = 8
const DRAG_THRESHOLD = 5
const EDGE_PAD = 8
const SNAP_MS = 320
const SNAP_EASE = 'cubic-bezier(0.34, 1.2, 0.64, 1)'

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
  } catch {
    // ignore
  }
  return { side: 'right', topPx: 16 }
}

function saveStored(data: Stored) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // ignore
  }
}

function clampTop(top: number, minTop: number): number {
  const min = Math.max(minTop, EDGE_PAD)
  const max = Math.max(min, window.innerHeight - ASSISTANT_FAB_SIZE - EDGE_PAD)
  return Math.min(Math.max(min, top), max)
}

export function useAssistantFabPosition(
  getContentLeft: () => number,
  getMinTop: () => number
) {
  const initial = loadStored()
  const side = ref<'left' | 'right'>(initial.side)
  const topPx = ref(clampTop(initial.topPx, getMinTop()))

  const isDragging = ref(false)
  const dragLeftPx = ref<number | null>(null)
  const dragTopPx = ref<number | null>(null)

  /** 松手后从当前位置动画贴到左/右缘 */
  const isSnapping = ref(false)
  const snapAnimating = ref(false)
  const snapLeftPx = ref<number | null>(null)
  const snapTopPx = ref<number | null>(null)
  let snapEndTimer: ReturnType<typeof setTimeout> | null = null

  let pointerDown = false
  let hasDragged = false
  let grabOffsetX = 0
  let grabOffsetY = 0
  let dragStartX = 0
  let dragStartY = 0
  let suppressClick = false

  function persist() {
    saveStored({ side: side.value, topPx: topPx.value })
  }

  function prefersReducedMotion(): boolean {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  function cancelSnapAnimation() {
    if (snapEndTimer != null) {
      clearTimeout(snapEndTimer)
      snapEndTimer = null
    }
    isSnapping.value = false
    snapAnimating.value = false
    snapLeftPx.value = null
    snapTopPx.value = null
  }

  function startSnapToEdge(fromLeft: number, fromTop: number, toLeft: number, toTop: number) {
    cancelSnapAnimation()
    const dist = Math.hypot(toLeft - fromLeft, toTop - fromTop)
    if (dist < 0.5 || prefersReducedMotion()) {
      return
    }
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
        }, SNAP_MS + 40)
      })
    })
  }

  function clampHorizontal(left: number): number {
    const max = Math.max(EDGE_PAD, window.innerWidth - ASSISTANT_FAB_SIZE - EDGE_PAD)
    return Math.min(Math.max(EDGE_PAD, left), max)
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
      }
    }
    if (isSnapping.value && snapLeftPx.value != null && snapTopPx.value != null) {
      const trans =
        snapAnimating.value
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
      }
    }
    const top = clampTop(topPx.value, getMinTop())
    if (side.value === 'left') {
      return {
        position: 'fixed' as const,
        left: `${getContentLeft() + LEFT_GAP}px`,
        top: `${top}px`,
        right: 'auto' as const,
        zIndex: 50,
        touchAction: 'none' as const,
        transition: 'none',
      }
    }
    return {
      position: 'fixed' as const,
      right: `${RIGHT_GAP}px`,
      top: `${top}px`,
      left: 'auto' as const,
      zIndex: 50,
      touchAction: 'none' as const,
      transition: 'none',
    }
  })

  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0) return
    cancelSnapAnimation()
    const el = e.currentTarget as HTMLElement
    const rect = el.getBoundingClientRect()
    grabOffsetX = e.clientX - rect.left
    grabOffsetY = e.clientY - rect.top
    dragStartX = e.clientX
    dragStartY = e.clientY
    pointerDown = true
    hasDragged = false
    dragLeftPx.value = null
    dragTopPx.value = null
    isDragging.value = false
    el.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: PointerEvent) {
    if (!pointerDown) return
    const dx = e.clientX - dragStartX
    const dy = e.clientY - dragStartY
    if (!hasDragged && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      hasDragged = true
      isDragging.value = true
    }
    if (hasDragged) {
      dragLeftPx.value = clampHorizontal(e.clientX - grabOffsetX)
      dragTopPx.value = clampTop(e.clientY - grabOffsetY, getMinTop())
    }
  }

  function onPointerUp(e: PointerEvent) {
    if (!pointerDown) return
    const el = e.currentTarget as HTMLElement
    pointerDown = false
    try {
      el.releasePointerCapture(e.pointerId)
    } catch {
      // ignore
    }

    if (hasDragged) {
      const left = dragLeftPx.value ?? 0
      const top = clampTop(dragTopPx.value ?? topPx.value, getMinTop())
      const centerX = left + ASSISTANT_FAB_SIZE / 2
      const nextSide = centerX < window.innerWidth / 2 ? 'left' : 'right'
      const toLeft =
        nextSide === 'left'
          ? getContentLeft() + LEFT_GAP
          : window.innerWidth - ASSISTANT_FAB_SIZE - RIGHT_GAP
      side.value = nextSide
      topPx.value = top
      suppressClick = true
      persist()
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

  /** @returns true 表示已消费（拖过后的合成 click），不应再打开助手 */
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
    cancelSnapAnimation()
    topPx.value = clampTop(topPx.value, getMinTop())
    persist()
  }

  watch(
    () => getMinTop(),
    () => {
      topPx.value = clampTop(topPx.value, getMinTop())
      persist()
    }
  )

  let raf = 0
  function scheduleResize() {
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => {
      raf = 0
      onResize()
    })
  }

  onMounted(() => {
    window.addEventListener('resize', scheduleResize, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('resize', scheduleResize)
    if (raf) cancelAnimationFrame(raf)
    cancelSnapAnimation()
  })

  return {
    fabStyle,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onFabClick,
  }
}
