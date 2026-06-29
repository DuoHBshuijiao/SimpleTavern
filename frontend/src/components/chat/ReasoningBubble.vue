<script setup lang="ts">
/**
 * ReasoningBubble - 思考链气泡
 *
 * 关键原则：
 * - 全文内容层始终挂载，不在展开/收起中途卸载
 * - 使用单一动画壳（AnimatedClipHeight）做 width/height 同步过渡
 * - 收起时允许 overflow 裁剪，待壳收缩结束后再展示小卡层
 * - 流式跟滚：不贴绝对底部，而是 scrollTop ≈ maxScroll − 一行高，把正在生成的那一行藏在视口底缘外；半截字等视觉问题可后续由 UI 调整
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AnimatedClipHeight from './AnimatedClipHeight.vue'
import { getLatestReasoningHighlight } from '../../utils/reasoningHighlights'

const props = withDefaults(
  defineProps<{
    content: string
    isStreaming?: boolean
    durationSec?: number | null
    streamingWindowHeight?: number
    streamingMaxHeightPx?: number | null
    smallCardHeight?: number
    smallCardWidth?: number
    expandedMaxVhRatio?: number
    expanded?: boolean
  }>(),
  {
    isStreaming: false,
    durationSec: null,
    streamingWindowHeight: 100,
    streamingMaxHeightPx: null,
    smallCardHeight: 35,
    smallCardWidth: 100,
    expandedMaxVhRatio: 0.6,
  },
)

const emit = defineEmits<{
  'update:expanded': [v: boolean]
  'expand-request': []
}>()

const internalExpanded = ref(false)
const isExpanded = computed<boolean>({
  get: () => (props.expanded === undefined ? internalExpanded.value : props.expanded),
  set: (v: boolean) => {
    if (props.expanded === undefined) internalExpanded.value = v
    emit('update:expanded', v)
  },
})

const showSmallCard = computed(() => !props.isStreaming && !isExpanded.value)
const useStreamingIntrinsicLayout = computed(() => props.isStreaming && !isExpanded.value)

const formattedDuration = computed(() => {
  const v = props.durationSec
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  return v.toFixed(1)
})

const scrollRef = ref<HTMLElement | null>(null)
const reasoningTextRef = ref<HTMLElement | null>(null)
const smallCardMeasureRef = ref<HTMLElement | null>(null)
const collapsedMeasuredWidth = ref<number | null>(null)
const topMaskVisible = ref(false)
const bottomMaskVisible = ref(false)
const smallCardVisualVisible = ref(showSmallCard.value)

let resizeObserver: ResizeObserver | null = null
let smallCardMeasureObserver: ResizeObserver | null = null
let autoScrollRaf: number | null = null

const streamingIntrinsicMaxHeightPx = computed(() => {
  let h = props.streamingWindowHeight
  const extra = props.streamingMaxHeightPx
  if (typeof extra === 'number' && Number.isFinite(extra) && extra > 0) {
    h = Math.min(h, extra)
  }
  return h
})

const rootLayoutClass = computed(() => {
  if (showSmallCard.value) return 'w-fit min-w-0 max-w-full self-start'
  if (useStreamingIntrinsicLayout.value) return 'w-fit min-w-0 max-w-full self-start'
  return 'w-full min-w-0 max-w-full self-start'
})

const collapsedOuterWidthPx = computed(() => {
  const m = collapsedMeasuredWidth.value
  return Math.max(props.smallCardWidth, m ?? props.smallCardWidth)
})

const frameMode = computed<'intrinsic' | 'intrinsic-fullColumn' | 'fullWidth' | 'fixed'>(() => {
  if (showSmallCard.value) return 'fixed'
  if (isExpanded.value) return 'fullWidth'
  if (useStreamingIntrinsicLayout.value) return 'intrinsic'
  return 'intrinsic-fullColumn'
})

const scrollInlineStyle = computed(() => {
  if (useStreamingIntrinsicLayout.value) {
    return { maxHeight: `${streamingIntrinsicMaxHeightPx.value}px` }
  }
  if (isExpanded.value) {
    // 底部留白已移出滚动区；扣除与 .reasoning-bubble --reasoning-tail-slot-h 一致
    return { maxHeight: `calc(${props.expandedMaxVhRatio * 100}vh - var(--reasoning-tail-slot-h))` }
  }
  return {}
})

const scrollLayoutClass = computed(() => {
  if (useStreamingIntrinsicLayout.value) {
    return 'relative min-h-0 reasoning-scroll--streaming-intrinsic'
  }
  if (isExpanded.value) {
    return 'relative min-h-0 reasoning-scroll--expanded'
  }
  return 'relative min-h-0'
})

/** 展开时置于底部遮罩区，便于滚到底后顺手收起；流式未展开仍用右上角 */
const toggleIconPositionClass = computed(() => {
  if (smallCardVisualVisible.value) {
    return 'right-1 top-1/2 h-5 w-5 -translate-y-1/2'
  }
  if (isExpanded.value) {
    return 'rotate-90 bottom-1 right-2 top-auto h-6 w-6'
  }
  return 'top-2 right-2 h-6 w-6'
})

/** 收起为小卡时始终隐藏全文层（含收壳过渡），避免未 settled 前露出正文 */
const hideFullContent = computed(() => showSmallCard.value)

/** 小卡稳定后隐藏；流式/展开/收壳过渡中仍显示（与 hideFullContent 解耦） */
const showGradientMasks = computed(() => !showSmallCard.value || !smallCardVisualVisible.value)

const latestReasoningHighlight = computed(() =>
  getLatestReasoningHighlight(String(props.content ?? ''), { isStreaming: props.isStreaming }),
)

/** 有摘要文案（小卡态不展示思考区，故不启用）；流式/展开均在滚动区下方兄弟节点挂载尾槽 */
const hasReasoningHighlight = computed(() => {
  const t = latestReasoningHighlight.value
  return t != null && t.length > 0 && !showSmallCard.value
})

function teardownSmallCardMeasureObserver() {
  smallCardMeasureObserver?.disconnect()
  smallCardMeasureObserver = null
}

function measureCollapsedSmallCardWidth() {
  const el = smallCardMeasureRef.value
  if (!el) return
  const w = Math.ceil(el.getBoundingClientRect().width) + 1
  if (w > 0) collapsedMeasuredWidth.value = w
}

function scheduleMeasureCollapsedWidth() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      measureCollapsedSmallCardWidth()
    })
  })
}

function getLineHeightPx(el: HTMLElement | null): number {
  if (!el) return 20
  const cs = window.getComputedStyle(el)
  const lh = parseFloat(cs.lineHeight)
  if (Number.isFinite(lh) && lh > 0) return lh
  const fs = parseFloat(cs.fontSize)
  return Number.isFinite(fs) && fs > 0 ? fs * 1.5 : 20
}

function updateMaskVisibility() {
  const el = scrollRef.value
  if (!el) {
    topMaskVisible.value = false
    bottomMaskVisible.value = false
    return
  }
  topMaskVisible.value = el.scrollTop > 2
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
  bottomMaskVisible.value = el.scrollTop < maxScroll - 2
}

/** 流式阶段：跟滚但故意留一行不露出（隐藏正在生成行），平滑滚动 */
function scheduleStreamingFollowScroll() {
  if (!props.isStreaming) return
  if (autoScrollRaf != null) cancelAnimationFrame(autoScrollRaf)
  autoScrollRaf = requestAnimationFrame(() => {
    autoScrollRaf = null
    requestAnimationFrame(() => {
      const el = scrollRef.value
      if (!el) return
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
      if (maxScroll <= 0) {
        updateMaskVisibility()
        return
      }
      const lh = getLineHeightPx(reasoningTextRef.value || el)
      const target = Math.max(0, maxScroll - lh)
      try {
        el.scrollTo({ top: target, behavior: 'smooth' })
      } catch {
        el.scrollTop = target
      }
      requestAnimationFrame(updateMaskVisibility)
    })
  })
}

function onRootClick(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.reasoning-toggle-icon')) return
  if (isExpanded.value) return
  isExpanded.value = true
  emit('expand-request')
}

function toggleExpanded(e: MouseEvent) {
  e.stopPropagation()
  isExpanded.value = !isExpanded.value
}

watch(
  () => showSmallCard.value,
  (collapsed, prev) => {
    if (!collapsed) {
      smallCardVisualVisible.value = false
      return
    }
    if (prev === false || prev === undefined) {
      smallCardVisualVisible.value = false
      return
    }
    smallCardVisualVisible.value = true
  },
  { immediate: true },
)

function handleFrameSettled() {
  if (showSmallCard.value) {
    smallCardVisualVisible.value = true
  }
}

watch(
  () => props.content,
  () => {
    if (props.isStreaming) {
      scheduleStreamingFollowScroll()
      nextTick(updateMaskVisibility)
    } else if (isExpanded.value) {
      nextTick(updateMaskVisibility)
    }
  },
)

watch(
  () => props.isStreaming,
  (streaming) => {
    if (streaming) {
      scheduleStreamingFollowScroll()
      nextTick(updateMaskVisibility)
    }
  },
)

watch(
  () => [showSmallCard.value, formattedDuration.value] as const,
  async () => {
    await nextTick()
    teardownSmallCardMeasureObserver()
    const el = smallCardMeasureRef.value
    if (el && typeof ResizeObserver !== 'undefined') {
      smallCardMeasureObserver = new ResizeObserver(() => measureCollapsedSmallCardWidth())
      smallCardMeasureObserver.observe(el)
    }
    scheduleMeasureCollapsedWidth()
  },
  { immediate: true },
)

onMounted(() => {
  if (props.isStreaming) {
    scheduleStreamingFollowScroll()
  }
  nextTick(updateMaskVisibility)
  if (typeof ResizeObserver !== 'undefined' && scrollRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (props.isStreaming) scheduleStreamingFollowScroll()
      updateMaskVisibility()
    })
    resizeObserver.observe(scrollRef.value)
  }
})

onBeforeUnmount(() => {
  if (autoScrollRaf != null) cancelAnimationFrame(autoScrollRaf)
  resizeObserver?.disconnect()
  resizeObserver = null
  teardownSmallCardMeasureObserver()
})
</script>

<template>
    <div
      class="reasoning-bubble reasoning-bubble-surface rounded-lg text-xs leading-relaxed relative overflow-hidden"
      :class="[
        rootLayoutClass,
        showSmallCard ? '' : (isExpanded ? '' : 'cursor-pointer'),
        !hasReasoningHighlight ? 'reasoning-bubble--tail-collapsed' : '',
      ]"
      @click="onRootClick"
    >
    <div
      ref="smallCardMeasureRef"
      class="reasoning-small-card-measure absolute left-0 top-0 z-[-1] flex items-center gap-1 pl-2 pr-7 whitespace-nowrap opacity-0 pointer-events-none select-none"
      aria-hidden="true"
    >
      <span class="inline-flex items-center gap-1 text-[var(--color-text-muted)]">
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="shrink-0">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        <template v-if="formattedDuration !== null">已思考 {{ formattedDuration }} 秒</template>
        <template v-else>已思考</template>
      </span>
    </div>

    <AnimatedClipHeight
      class="reasoning-frame"
      :mode="frameMode"
      :fixed-width-px="collapsedOuterWidthPx"
      :fixed-height-px="props.smallCardHeight"
      :relax-height-dead-zone="props.isStreaming"
      @settled="handleFrameSettled"
    >
      <div class="reasoning-clip-stack flex min-h-0 min-w-0 flex-col">
        <div
          ref="scrollRef"
          class="reasoning-scroll overflow-y-auto overflow-x-hidden px-3 py-2.5 whitespace-pre-wrap break-words transition-opacity duration-200"
          :class="[scrollLayoutClass, hideFullContent ? 'opacity-0 pointer-events-none' : 'opacity-100']"
          :style="scrollInlineStyle"
          @scroll="updateMaskVisibility"
        >
          <div
            ref="reasoningTextRef"
            class="reasoning-text"
            :class="props.isStreaming && !String(props.content || '').trim() ? 'reasoning-text--streaming-empty' : ''"
          >
            {{ content }}
          </div>
        </div>
        <div
          v-if="hasReasoningHighlight"
          class="reasoning-tail-slot"
          aria-label="思考要点"
        >
          <Transition name="reasoning-tail-fade" mode="out-in">
            <p
              v-if="latestReasoningHighlight != null"
              :key="latestReasoningHighlight"
              class="reasoning-tail-caption"
            >
              {{ latestReasoningHighlight }}
            </p>
          </Transition>
        </div>
      </div>

      <template #measure>
        <div class="reasoning-clip-stack flex min-h-0 min-w-0 flex-col">
          <div
            class="reasoning-scroll reasoning-scroll--measure overflow-y-auto overflow-x-hidden px-3 py-2.5 whitespace-pre-wrap break-words"
            :class="[scrollLayoutClass]"
            :style="scrollInlineStyle"
          >
            <div
              class="reasoning-text"
              :class="props.isStreaming && !String(props.content || '').trim() ? 'reasoning-text--streaming-empty' : ''"
            >
              {{ content }}
            </div>
          </div>
          <div
            v-if="hasReasoningHighlight"
            class="reasoning-tail-slot"
            aria-label="思考要点"
          >
            <Transition name="reasoning-tail-fade" mode="out-in">
              <p
                v-if="latestReasoningHighlight != null"
                :key="latestReasoningHighlight"
                class="reasoning-tail-caption"
              >
                {{ latestReasoningHighlight }}
              </p>
            </Transition>
          </div>
        </div>
      </template>
    </AnimatedClipHeight>

    <div
      class="reasoning-small-card absolute inset-0 flex items-center gap-1 whitespace-nowrap pl-2 pr-7 transition-opacity duration-200"
      :class="smallCardVisualVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'"
      :aria-hidden="!smallCardVisualVisible"
    >
      <span class="inline-flex shrink-0 items-center gap-1 text-[var(--color-text-muted)]">
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="shrink-0">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        <template v-if="formattedDuration !== null">已思考 {{ formattedDuration }} 秒</template>
        <template v-else>已思考</template>
      </span>
    </div>

    <div
      v-if="showGradientMasks"
      class="reasoning-mask reasoning-mask-top"
      :class="topMaskVisible ? 'opacity-100' : 'opacity-0'"
      aria-hidden="true"
    />
    <div
      v-if="showGradientMasks"
      class="reasoning-mask reasoning-mask-bottom"
      :class="bottomMaskVisible ? 'opacity-100' : 'opacity-0'"
      aria-hidden="true"
    />

    <button
      type="button"
      class="reasoning-toggle-icon absolute z-[11] flex items-center justify-center rounded transition-all duration-200"
      :class="toggleIconPositionClass"
      :aria-label="isExpanded ? '收起思考' : '展开思考'"
      @click="toggleExpanded"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.reasoning-bubble {
  will-change: width, height;
  /* 与收起按钮 bottom-1 + h-6 对齐尾槽垂直中心，供外部尾槽与底遮罩共用 */
  --reasoning-tail-slot-h: calc(0.5rem + 1.5rem);
  --reasoning-mask-bottom: var(--reasoning-tail-slot-h);
}
.reasoning-bubble--tail-collapsed {
  --reasoning-tail-slot-h: 0px;
  --reasoning-mask-bottom: 0px;
}
.reasoning-frame {
  max-width: 100%;
}
.reasoning-scroll {
  scroll-behavior: smooth;
}
.reasoning-scroll--streaming-intrinsic {
  scroll-behavior: auto;
}
.reasoning-scroll--expanded {
  scroll-behavior: smooth;
}
.reasoning-scroll--measure {
  transition: none !important;
}
.reasoning-toggle-icon {
  background: color-mix(in srgb, var(--color-reasoning-bubble-bg) 88%, transparent);
}
.reasoning-toggle-icon:hover {
  background: color-mix(in srgb, var(--color-text) 12%, transparent);
}
.reasoning-scroll::-webkit-scrollbar {
  width: 4px;
}
.reasoning-scroll::-webkit-scrollbar-thumb {
  background-color: color-mix(in srgb, var(--color-text-muted) 24%, transparent);
  border-radius: 4px;
}
.reasoning-tail-slot {
  flex-shrink: 0;
  height: var(--reasoning-tail-slot-h);
  min-height: var(--reasoning-tail-slot-h);
  box-sizing: border-box;
  padding-left: 0.75rem;
  padding-right: 2rem;
  display: grid;
  grid-template-rows: 1fr;
  align-items: center;
  justify-items: start;
  min-width: 0;
  position: relative;
  z-index: 1;
  background-color: var(--color-reasoning-bubble-bg);
  border-top: 1px solid var(--color-reasoning-bubble-border, transparent);
}
.reasoning-tail-caption {
  margin: 0;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  font-weight: 400;
  font-size: 0.875rem;
  line-height: 1.25;
  color: color-mix(in srgb, var(--color-text-muted) 88%, var(--color-primary) 12%);
}
.reasoning-tail-fade-enter-active,
.reasoning-tail-fade-leave-active {
  transition: opacity 200ms ease;
}
.reasoning-tail-fade-enter-from,
.reasoning-tail-fade-leave-to {
  opacity: 0;
}
.reasoning-text {
  overflow-wrap: anywhere;
}
.reasoning-text--streaming-empty {
  min-height: 1.25rem;
}
.reasoning-mask {
  position: absolute;
  left: 0;
  right: 0;
  pointer-events: none;
  transition: opacity 200ms ease-out;
  z-index: 2;
}
.reasoning-mask-top {
  top: 0;
  height: 26px;
  background-color: color-mix(in srgb, var(--color-reasoning-bubble-bg) 82%, transparent);
  box-shadow: inset 0 10px 14px -10px color-mix(in srgb, var(--color-primary) 32%, transparent);
}
.reasoning-mask-bottom {
  /* 底缘与尾槽顶对齐（兄弟尾槽在滚动区下） */
  bottom: var(--reasoning-mask-bottom);
  height: 32px;
  background-color: color-mix(in srgb, var(--color-reasoning-bubble-bg) 82%, transparent);
  box-shadow: inset 0 -10px 14px -10px color-mix(in srgb, var(--color-primary) 32%, transparent);
}
</style>
