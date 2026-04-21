<script setup lang="ts">
/**
 * 共享气泡尺寸动画壳：
 * - 可见内容与测量内容使用等价布局语义
 * - 内容布局宽度独立于当前 frame 宽度，避免动画过程中反复重排
 * - frame 只负责 width/height 过渡与 overflow 裁剪
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type FrameMode = 'intrinsic' | 'intrinsic-fullColumn' | 'fullWidth' | 'fixed'

const props = withDefaults(
  defineProps<{
    mode?: FrameMode
    fixedWidthPx?: number | null
    fixedHeightPx?: number | null
    durationMs?: number
    easing?: string
    relaxHeightDeadZone?: boolean
    contentFullWidth?: boolean
  }>(),
  {
    mode: 'intrinsic-fullColumn',
    fixedWidthPx: null,
    fixedHeightPx: null,
    durationMs: 520,
    easing: 'cubic-bezier(0.33, 1, 0.68, 1)',
    relaxHeightDeadZone: false,
    contentFullWidth: false,
  },
)

const emit = defineEmits<{
  settled: []
}>()

const hostRef = ref<HTMLElement | null>(null)
const frameRef = ref<HTMLElement | null>(null)
const visibleRef = ref<HTMLElement | null>(null)
const measureRef = ref<HTMLElement | null>(null)
let ro: ResizeObserver | null = null
let firstSync = true
let lastW = 0
let lastH = 0
let lastContentLayoutWidth = 0
let settleRaf = 0

const hostInlineStyle = computed<Record<string, string>>(() => {
  if (props.mode === 'fullWidth') {
    return { display: 'block', width: '100%', maxWidth: '100%' }
  }
  return { display: 'inline-block', width: 'auto', maxWidth: '100%' }
})

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function applyLayoutWidth(el: HTMLElement, width: number) {
  const w = Math.max(1, Math.ceil(width))
  el.style.width = `${w}px`
  el.style.minWidth = `${w}px`
  el.style.maxWidth = `${w}px`
}

function clearLayoutWidth(el: HTMLElement) {
  el.style.width = ''
  el.style.minWidth = ''
  el.style.maxWidth = ''
}

const CHAT_BUBBLE_COLUMN = '[data-chat-bubble-column]'
/** 正文气泡外壳：排版预算 = 列 content 宽减壳 padding/border，勿读 w-fit 壳当前 client 宽（会与测量闭环导致极窄换行/振荡） */
const CHAT_BUBBLE_SHELL = '[data-chat-bubble-shell]'

function innerContentWidthPx(el: HTMLElement): number {
  const cs = window.getComputedStyle(el)
  const paddingLeft = parseFloat(cs.paddingLeft) || 0
  const paddingRight = parseFloat(cs.paddingRight) || 0
  return Math.max(0, Math.floor(el.clientWidth - paddingLeft - paddingRight))
}

function horizontalPaddingBorderPx(el: HTMLElement): number {
  const cs = window.getComputedStyle(el)
  const pl = parseFloat(cs.paddingLeft) || 0
  const pr = parseFloat(cs.paddingRight) || 0
  const bl = parseFloat(cs.borderLeftWidth) || 0
  const br = parseFloat(cs.borderRightWidth) || 0
  return pl + pr + bl + br
}

function getAvailableWidthPx(): number {
  const host = hostRef.value
  if (!host) return 0
  const col = host.closest(CHAT_BUBBLE_COLUMN) as HTMLElement | null
  if (col) {
    const colInner = innerContentWidthPx(col)
    const shell = host.closest(CHAT_BUBBLE_SHELL) as HTMLElement | null
    if (shell) {
      const inset = horizontalPaddingBorderPx(shell)
      const w = Math.floor(colInner - inset)
      if (w >= 8) return w
    }
    if (colInner >= 8) return colInner
  }
  const parent = host.parentElement
  if (parent) {
    return innerContentWidthPx(parent)
  }
  return Math.max(0, Math.floor(host.getBoundingClientRect().width))
}

function measureTargetSize(): { width: number; height: number; contentWidth: number } | null {
  if (props.mode === 'fixed') {
    const w = Math.max(0, Math.ceil(props.fixedWidthPx ?? 0))
    const h = Math.max(0, Math.ceil(props.fixedHeightPx ?? 0))
    if (w <= 0 || h <= 0) return null
    return { width: w, height: h, contentWidth: Math.max(1, lastContentLayoutWidth || w) }
  }
  const measure = measureRef.value
  if (!measure) return null
  const available = getAvailableWidthPx()
  const targetEl = (measure.firstElementChild as HTMLElement | null) ?? measure
  if (props.mode === 'fullWidth' || props.mode === 'intrinsic-fullColumn') {
    const w = Math.max(1, available)
    applyLayoutWidth(measure, w)
  } else {
    clearLayoutWidth(measure)
    measure.style.width = 'max-content'
    measure.style.minWidth = '0px'
    measure.style.maxWidth = available > 0 ? `${available}px` : 'none'
  }
  const rect = targetEl.getBoundingClientRect()
  const width =
    props.mode === 'fullWidth'
      ? Math.max(1, available)
      : Math.max(1, Math.ceil(rect.width))
  const height = Math.max(1, Math.ceil(rect.height))
  const contentWidth =
    props.mode === 'fullWidth' || props.mode === 'intrinsic-fullColumn'
      ? Math.max(1, available)
      : width
  return { width, height, contentWidth }
}

/**
 * 离屏 measure 偶发略小于可见槽真实排版高度时，frame 会裁切正文。
 * 用可见根节点 scrollHeight 取 max 兜底；mode=fixed（思维链折叠小卡等）必须保持限高，不可抬升。
 */
function frameHeightForSync(measuredHeight: number): number {
  if (props.mode === 'fixed') return measuredHeight
  const vis = visibleRef.value
  if (!vis) return measuredHeight
  const vh = Math.ceil(vis.scrollHeight)
  return Math.max(measuredHeight, vh)
}

function syncVisibleContentWidth(targetContentWidth: number) {
  const visible = visibleRef.value
  if (!visible) return
  const contentWidth = Math.max(1, Math.ceil(targetContentWidth))
  lastContentLayoutWidth = contentWidth
  applyLayoutWidth(visible, contentWidth)
}

function clearVisibleContentWidth() {
  const visible = visibleRef.value
  if (!visible) return
  clearLayoutWidth(visible)
}

function scheduleSettledCheck() {
  if (settleRaf) cancelAnimationFrame(settleRaf)
  settleRaf = requestAnimationFrame(() => {
    settleRaf = 0
    const frame = frameRef.value
    if (!frame) return
    const target = measureTargetSize()
    if (!target) return
    const frameH = frameHeightForSync(target.height)
    const currentW = frame.getBoundingClientRect().width
    const currentH = frame.getBoundingClientRect().height
    if (Math.abs(currentW - target.width) < 1 && Math.abs(currentH - frameH) < 1) {
      // keep explicit dimensions as the new stable baseline, but make sure content layout width matches target semantics
      syncVisibleContentWidth(target.contentWidth)
      emit('settled')
    }
  })
}

function onFrameTransitionEnd(event: TransitionEvent) {
  if (event.target !== frameRef.value) return
  if (event.propertyName !== 'width' && event.propertyName !== 'height') return
  scheduleSettledCheck()
}

function sync() {
  const frame = frameRef.value
  if (!frame) return
  const target = measureTargetSize()
  if (!target) return
  syncVisibleContentWidth(target.contentWidth)
  const frameH = frameHeightForSync(target.height)
  if (reducedMotion()) {
    frame.style.width = `${target.width}px`
    frame.style.height = `${frameH}px`
    frame.style.overflow = ''
    frame.style.transition = ''
    lastW = target.width
    lastH = frameH
    return
  }
  if (firstSync) {
    firstSync = false
    lastW = target.width
    lastH = frameH
    frame.style.overflow = 'hidden'
    frame.style.transition = 'none'
    frame.style.width = `${target.width}px`
    frame.style.height = `${frameH}px`
    requestAnimationFrame(() => {
      frame.style.transition = ''
    })
    return
  }
  const dw = Math.abs(target.width - lastW)
  const dh = Math.abs(frameH - lastH)
  const hDead = props.relaxHeightDeadZone ? 0.01 : 1
  const changedW = dw >= 0.01
  const changedH = dh >= hDead
  if (!changedW && !changedH) return

  frame.style.overflow = 'hidden'
  const segs: string[] = []
  if (changedW) segs.push(`width ${props.durationMs}ms ${props.easing}`)
  if (changedH) segs.push(`height ${props.durationMs}ms ${props.easing}`)
  frame.style.transition = segs.join(', ')
  if (changedW) frame.style.width = `${target.width}px`
  if (changedH) frame.style.height = `${frameH}px`
  if (changedW) lastW = target.width
  if (changedH) lastH = frameH
  scheduleSettledCheck()
}

function attach() {
  ro?.disconnect()
  const v = visibleRef.value
  const m = measureRef.value
  const h = hostRef.value
  if (!v || !m || !h) return
  ro = new ResizeObserver(() => {
    nextTick(sync)
  })
  ro.observe(v)
  ro.observe(m)
  ro.observe(h)
  nextTick(sync)
}

watch([hostRef, frameRef, visibleRef, measureRef], () => {
  if (!hostRef.value || !frameRef.value || !visibleRef.value || !measureRef.value) {
    ro?.disconnect()
    ro = null
    return
  }
  firstSync = true
  attach()
}, { flush: 'post' })

watch(
  () => [props.mode, props.fixedWidthPx, props.fixedHeightPx, props.durationMs, props.easing, props.contentFullWidth] as const,
  () => nextTick(sync),
)

function onResize() {
  nextTick(sync)
}

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (settleRaf) cancelAnimationFrame(settleRaf)
  clearVisibleContentWidth()
  ro?.disconnect()
  ro = null
})
</script>

<template>
  <div ref="hostRef" class="animated-clip-size-host" :style="hostInlineStyle">
    <div ref="frameRef" class="animated-clip-size-frame" @transitionend="onFrameTransitionEnd">
      <div ref="visibleRef" class="animated-clip-size-visible">
        <slot />
      </div>
    </div>
    <div class="animated-clip-size-measure-stage" aria-hidden="true">
      <div ref="measureRef" class="animated-clip-size-measure">
        <slot name="measure">
          <slot />
        </slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animated-clip-size-host {
  position: relative;
  min-width: 0;
  vertical-align: top;
}
.animated-clip-size-frame {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}
.animated-clip-size-visible {
  display: block;
  min-width: 0;
  max-width: none;
}
.animated-clip-size-measure-stage {
  position: fixed;
  left: -100000px;
  top: -100000px;
  min-width: 0;
  width: auto;
  height: auto;
  pointer-events: none;
  visibility: hidden;
  overflow: visible;
}
.animated-clip-size-measure {
  display: block;
  min-width: 0;
  max-width: none;
}
</style>
