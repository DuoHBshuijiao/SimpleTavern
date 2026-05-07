<template>
  <div
    v-if="capsules.length > 0"
    class="group relative z-20 min-w-0 flex w-full shrink-0 flex-col overflow-visible"
  >
    <div class="min-w-0 overflow-visible px-[18px] py-1.5">
      <TransitionGroup
        tag="div"
        name="svbar-cap"
        class="relative flex min-w-0 flex-wrap items-center gap-2"
        :ref="bindPillTrackRef"
      >
        <span
          v-for="(cap, i) in capsules"
          :key="capsuleRowKey(cap, i)"
          data-svbar-pill
          class="relative inline-flex max-w-[min(100vw,20rem)] shrink-0 select-none items-center gap-1.5 overflow-hidden rounded-full border px-2.5 py-1 backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.45] transition-colors duration-300"
          :class="[
            cap.flashing
              ? 'border-[var(--color-brand-a50)] bg-[var(--color-brand-a30)]'
              : 'border-[var(--color-border)]/80 bg-surface-overlay',
          ]"
        >
          <span
            v-if="showScan"
            class="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-[inherit]"
            aria-hidden="true"
          >
            <span
              class="svbar-pill-scan-band"
              :style="beamStyleFor(i)"
            />
          </span>
          <span class="relative z-[1] inline-flex min-w-0 items-center gap-1.5">
            <Transition name="svbar-cap-text" mode="out-in">
              <span
                :key="cap.field"
                class="svbar-cap-text-outer inline-block shrink-0 text-xs leading-4 text-[var(--color-text-muted)]"
              >
                <span class="block whitespace-nowrap">{{ cap.field }}</span>
              </span>
            </Transition>
            <Transition name="svbar-cap-text" mode="out-in">
              <span
                :key="String(cap.value)"
                class="svbar-cap-text-outer inline-block min-w-0 max-w-[12rem] text-xs font-medium leading-4 text-[var(--color-text)]"
              >
                <span class="block truncate">{{ cap.value }}</span>
              </span>
            </Transition>
          </span>
        </span>

        <!-- MVU 运行指示器（与胶囊同一 flex-wrap 流，尾部） -->
        <span
          v-if="isRunning"
          key="svbar-running"
          class="inline-flex h-4 w-4 shrink-0 items-center justify-center"
          aria-hidden="true"
        >
          <span class="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--color-text-muted)] border-t-transparent" />
        </span>

        <!-- 面板开关 -->
        <button
          key="svbar-panel"
          type="button"
          class="ml-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[var(--color-text-muted)] transition-colors transition-opacity hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
          :class="preferHoverChrome ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'"
          aria-label="MVU 工作日志"
          @click="$emit('toggle-panel')"
        >
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { usePreferHoverChrome } from '../../composables/usePreferHoverChrome'
import { useMvuStore, type CapsuleItem } from '../../stores/mvu'
import { computeFlexWrapExtraHeight } from '../../utils/stateBarWrapExtra'

/** 与 CSS 动画周期一致 */
const SCAN_PERIOD_MS = 2000
const SCAN_BEAM_WIDTH_PX = 76

const { preferHoverChrome } = usePreferHoverChrome()
const mvuStore = useMvuStore()

const props = withDefaults(defineProps<{
  capsules: CapsuleItem[]
  isRunning: boolean
  /** 当前会话 id；传入后可在切会话/disconnect 时避免误把 isRunning 回落当成「本轮 MVU 收尾扫描」 */
  chatId?: string | null
}>(), {
  chatId: null,
})

const emit = defineEmits<{
  'toggle-panel': []
  'wrap-extra-height-change': [px: number]
}>()

/** 稳定列表 key：同表重复 field 时用索引区分，避免 Vue 复用节点导致无过渡 */
function capsuleRowKey(cap: CapsuleItem, index: number): string {
  return `${cap.field}\u0000${index}`
}

/** 每粒胶囊在其 flex 视觉行内的水平起点，以及该视觉行的总宽（用于收尾扫描） */
type PillScanMetric = { start: number, lineWidth: number }

const pillTrackEl = ref<HTMLElement | null>(null)
const pillMetrics = ref<PillScanMetric[]>([])

let pillTrackResizeObserver: ResizeObserver | null = null
let scanFrameId: number | null = null
let scanStartedAtMs = 0
let scanStopAtMs: number | null = null

function getTransitionGroupRoot(el: Element | ComponentPublicInstance | null): HTMLElement | null {
  if (el == null) return null
  if (el instanceof HTMLElement) return el
  const inst = el as ComponentPublicInstance & { $el?: HTMLElement }
  return inst.$el instanceof HTMLElement ? inst.$el : null
}

function bindPillTrackRef(el: Element | ComponentPublicInstance | null) {
  const root = getTransitionGroupRoot(el)
  pillTrackEl.value = root
  if (pillTrackResizeObserver) {
    pillTrackResizeObserver.disconnect()
    pillTrackResizeObserver = null
  }
  if (root && typeof ResizeObserver !== 'undefined') {
    pillTrackResizeObserver = new ResizeObserver(() => {
      computePillMetrics()
    })
    pillTrackResizeObserver.observe(root)
  }
  void nextTick(() => computePillMetrics())
}

function reportWrapExtraHeight(row: HTMLElement | null) {
  if (!row) {
    emit('wrap-extra-height-change', 0)
    return
  }

  const items = Array.from(row.children)
    .filter((el): el is HTMLElement => el instanceof HTMLElement)
    .map((el) => ({
      offsetTop: el.offsetTop,
      offsetHeight: el.offsetHeight,
      offsetWidth: el.offsetWidth,
    }))

  emit('wrap-extra-height-change', computeFlexWrapExtraHeight(items))
}

/** 将 flex-wrap 后同一视觉行的胶囊归桶（offsetTop 容差 2px，兼容子像素） */
function bucketPillsByVisualLine(pills: HTMLElement[]): HTMLElement[][] {
  const sorted = [...pills].sort((a, b) => a.offsetTop - b.offsetTop || a.offsetLeft - b.offsetLeft)
  const buckets: HTMLElement[][] = []
  for (const p of sorted) {
    let placed = false
    for (const b of buckets) {
      const ref = b[0]!
      if (Math.abs(p.offsetTop - ref.offsetTop) <= 2) {
        b.push(p)
        placed = true
        break
      }
    }
    if (!placed) buckets.push([p])
  }
  return buckets
}

/**
 * 测量每粒胶囊在其视觉行内的水平位置；flex-wrap 多行时按行分别算宽度。
 * 扫描相位全局一致，每行独立映射水平位移。
 */
function computePillMetrics() {
  const row = pillTrackEl.value
  const n = props.capsules.length
  if (!row || n === 0) {
    pillMetrics.value = []
    reportWrapExtraHeight(null)
    return
  }
  reportWrapExtraHeight(row)
  const pills = Array.from(row.children).filter(
    (el): el is HTMLElement => el instanceof HTMLElement && el.hasAttribute('data-svbar-pill'),
  )
  if (pills.length !== n) {
    pillMetrics.value = []
    return
  }
  const buckets = bucketPillsByVisualLine(pills)
  const lineInfo = new Map<HTMLElement, { lineLeft: number, lineWidth: number }>()
  for (const b of buckets) {
    const lineLeft = Math.min(...b.map((p) => p.offsetLeft))
    const lineRight = Math.max(...b.map((p) => p.offsetLeft + p.offsetWidth))
    const lineWidth = lineRight - lineLeft
    if (lineWidth < 4) {
      pillMetrics.value = []
      return
    }
    for (const p of b) {
      lineInfo.set(p, { lineLeft, lineWidth })
    }
  }
  pillMetrics.value = pills.map((pill) => {
    const info = lineInfo.get(pill)
    if (!info) return { start: 0, lineWidth: 0 }
    return {
      start: pill.offsetLeft - info.lineLeft,
      lineWidth: info.lineWidth,
    }
  })
}

/** 最近一次在本组件内观测到的 isRunning=true 所对应的会话（用于区分 disconnect 与本轮 MVU 正常结束） */
const lastRunningChatForTailRef = ref<string | null>(null)

const scanActive = ref(false)
const scanNowMs = ref(0)

const showScan = computed(() => scanActive.value)

function getNowMs(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function startScanCycle() {
  const now = getNowMs()
  scanStartedAtMs = now
  scanStopAtMs = null
  scanNowMs.value = now
  scanActive.value = true
  ensureScanFrame()
}

function finishScanAfterCurrentCycle() {
  if (!scanActive.value) return
  const now = getNowMs()
  const elapsed = Math.max(0, now - scanStartedAtMs)
  scanStopAtMs = scanStartedAtMs + (Math.floor(elapsed / SCAN_PERIOD_MS) + 1) * SCAN_PERIOD_MS
  ensureScanFrame()
}

function stopScanImmediately() {
  scanActive.value = false
  scanStopAtMs = null
  if (scanFrameId != null) {
    cancelAnimationFrame(scanFrameId)
    scanFrameId = null
  }
}

function ensureScanFrame() {
  if (scanFrameId != null || !scanActive.value) return
  const tick = () => {
    const now = getNowMs()
    scanNowMs.value = now
    if (scanStopAtMs != null && now >= scanStopAtMs) {
      stopScanImmediately()
      return
    }
    scanFrameId = requestAnimationFrame(tick)
  }
  scanFrameId = requestAnimationFrame(tick)
}

function beamStyleFor(i: number): Record<string, string> {
  const metric = pillMetrics.value[i]
  const L = metric?.lineWidth ?? 0
  if (!metric || L < 4) {
    return {
      width: `${SCAN_BEAM_WIDTH_PX}px`,
      left: `${-SCAN_BEAM_WIDTH_PX}px`,
    }
  }
  const elapsed = Math.max(0, scanNowMs.value - scanStartedAtMs)
  const progress = (elapsed % SCAN_PERIOD_MS) / SCAN_PERIOD_MS
  const xBeam = -SCAN_BEAM_WIDTH_PX + progress * (L + SCAN_BEAM_WIDTH_PX * 2)
  const localX = xBeam - metric.start
  return {
    width: `${SCAN_BEAM_WIDTH_PX}px`,
    left: `${localX}px`,
  }
}

watch(
  () => props.chatId,
  () => {
    stopScanImmediately()
    lastRunningChatForTailRef.value = null
  },
)

watch(
  () => props.isRunning,
  (running, wasRunning) => {
    if (running) {
      startScanCycle()
      if (props.chatId != null && String(props.chatId).length > 0) {
        lastRunningChatForTailRef.value = props.chatId
      }
      return
    }
    if (!wasRunning) return

    if (!mvuStore.allowCapsuleScanTail) {
      stopScanImmediately()
      return
    }

    const chatStrict = props.chatId != null && String(props.chatId).length > 0
    if (
      chatStrict &&
      (lastRunningChatForTailRef.value == null || props.chatId !== lastRunningChatForTailRef.value)
    ) {
      stopScanImmediately()
      return
    }

    if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      stopScanImmediately()
      return
    }
    finishScanAfterCurrentCycle()
  },
  { immediate: true },
)

watch(
  () => [props.capsules.map((c) => `${c.field}\0${c.value}`).join('|'), showScan.value] as const,
  () => {
    void nextTick(() => computePillMetrics())
  },
)

onBeforeUnmount(() => {
  pillTrackResizeObserver?.disconnect()
  pillTrackResizeObserver = null
  stopScanImmediately()
  emit('wrap-extra-height-change', 0)
})
</script>

<style scoped>
/* 光束由 JS 的行级时钟给出 left，胶囊自身 overflow-hidden 负责裁剪成药丸 mask。 */
.svbar-pill-scan-band {
  position: absolute;
  top: 50%;
  height: 5200%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    transparent 18%,
    color-mix(in srgb, var(--color-text) 10%, transparent) 34%,
    color-mix(in srgb, var(--color-text) 28%, transparent) 44%,
    color-mix(in srgb, var(--color-brand-light) 42%, transparent) 50%,
    color-mix(in srgb, var(--color-text) 28%, transparent) 56%,
    color-mix(in srgb, var(--color-text) 10%, transparent) 66%,
    transparent 82%,
    transparent 100%
  );
  transform: translate(-50%, -50%) rotate(45deg);
  transform-origin: 50% 50%;
  will-change: transform;
}

@media (prefers-reduced-motion: reduce) {
  .svbar-pill-scan-band {
    display: none;
  }
}
</style>

<!-- 无 scoped：Transition/TransitionGroup 动态类名在部分环境下与 scoped 组合不稳定 -->
<style>
.svbar-cap-enter-active,
.svbar-cap-leave-active {
  transition:
    opacity 0.24s ease-out,
    transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
}

.svbar-cap-enter-from {
  opacity: 0;
  /* 从略偏右滑入，避免被横向 overflow 裁切 */
  transform: translateX(0.65rem);
}

.svbar-cap-enter-to {
  opacity: 1;
  transform: translateX(0);
}

.svbar-cap-leave-active {
  transition:
    opacity 0.18s ease-in,
    transform 0.22s ease-in;
}

.svbar-cap-leave-from {
  opacity: 1;
  transform: translateX(0);
}

.svbar-cap-leave-to {
  opacity: 0;
  transform: translateX(-0.35rem);
}

.svbar-cap-move {
  transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

.svbar-cap-text-enter-active,
.svbar-cap-text-leave-active {
  transition:
    opacity 0.2s ease-out,
    transform 0.26s cubic-bezier(0.22, 1, 0.36, 1);
}

.svbar-cap-text-enter-from,
.svbar-cap-text-leave-to {
  opacity: 0;
  transform: translateX(-0.4rem);
}

.svbar-cap-text-enter-to,
.svbar-cap-text-leave-from {
  opacity: 1;
  transform: translateX(0);
}

@media (prefers-reduced-motion: reduce) {
  .svbar-cap-enter-active,
  .svbar-cap-leave-active,
  .svbar-cap-move,
  .svbar-cap-text-enter-active,
  .svbar-cap-text-leave-active {
    transition: none;
  }

  .svbar-cap-enter-from,
  .svbar-cap-leave-to,
  .svbar-cap-text-enter-from,
  .svbar-cap-text-leave-to {
    opacity: 1;
    transform: none;
  }
}
</style>
