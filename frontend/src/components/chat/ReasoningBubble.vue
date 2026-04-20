<script setup lang="ts">
/**
 * ReasoningBubble - 思考链气泡（单聊 + 群聊 + 助手工作区复用）
 *
 * 模式：
 *   streaming  (isStreaming && !expanded): 宽随内容；max-w 继承父级；内层 max-h = streamingWindowHeight（默认 100px），可与 streamingMaxHeightPx 取更小值；超出内层滚动
 *   collapsed  (!isStreaming && !expanded): 高度 smallCardHeight，宽度不小于 smallCardWidth，按「已思考 x.x 秒」文案测量
 *   expanded   (expanded): height = min(contentHeight, 视口×expandedMaxVhRatio)，全宽可滚动；高度下界见 computeExpandedHeight
 *
 * 尺寸动画策略：
 *   - 收起/展开：外层 height/width 由 JS 写像素，CSS transition
 *   - 流式未展开：外层高度由内容决定（不写死像素），结束收小卡时切回像素高度
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    content: string
    isStreaming?: boolean
    durationSec?: number | null
    /**
     * 流式未展开时内层滚动区 max-height（px），默认 100；与 expanded 态上限无关。
     */
    streamingWindowHeight?: number
    /**
     * 可选：与 streamingWindowHeight 取 min，作为更严的流式未展开高度上限（px）。
     */
    streamingMaxHeightPx?: number | null
    /** 收起小卡片高度（px） */
    smallCardHeight?: number
    /** 收起态最小宽度（px）；实际宽度按文案测量，不小于该值 */
    smallCardWidth?: number
    /** 展开时的最大高度比例（相对视口高度）；流式未展开限高见 streamingWindowHeight */
    expandedMaxVhRatio?: number
    /** 由外部控制展开；若未传入则使用组件内部 state */
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
  /** 点击气泡体（非按钮）时触发；父组件可用于驱动 expandedReasoningMessageId */
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

/** 是否展示为「已思考 x.x 秒」小卡片：仅在未流式且未展开时 */
const showSmallCard = computed(() => !props.isStreaming && !isExpanded.value)

/** 流式且未展开：内容撑开外层，内层 max-height 封顶 + 超出滚动 */
const useStreamingIntrinsicLayout = computed(() => props.isStreaming && !isExpanded.value)

const formattedDuration = computed(() => {
  const v = props.durationSec
  if (typeof v !== 'number' || !Number.isFinite(v)) return null
  return v.toFixed(1)
})

const scrollRef = ref<HTMLElement | null>(null)
const smallCardMeasureRef = ref<HTMLElement | null>(null)
/** 收起态测量层宽度（px）；未测量前为 null，外层用 smallCardWidth */
const collapsedMeasuredWidth = ref<number | null>(null)
const currentHeight = ref<number>(props.smallCardHeight)
const topMaskVisible = ref(false)
const bottomMaskVisible = ref(false)

const streamingIntrinsicMaxHeightPx = computed(() => {
  let h = props.streamingWindowHeight
  const extra = props.streamingMaxHeightPx
  if (typeof extra === 'number' && Number.isFinite(extra) && extra > 0) {
    h = Math.min(h, extra)
  }
  return h
})

const rootLayoutClass = computed(() => {
  if (showSmallCard.value) {
    return 'min-w-0 max-w-full'
  }
  if (isExpanded.value) {
    return 'w-full min-w-0 max-w-full'
  }
  return 'w-fit min-w-0 max-w-full self-start'
})

const collapsedOuterWidthPx = computed(() => {
  const m = collapsedMeasuredWidth.value
  return Math.max(props.smallCardWidth, m ?? props.smallCardWidth)
})

const rootInlineStyle = computed(() => {
  if (showSmallCard.value) {
    return {
      height: `${currentHeight.value}px`,
      width: `${collapsedOuterWidthPx.value}px`,
    }
  }
  if (useStreamingIntrinsicLayout.value) {
    return {}
  }
  return { height: `${currentHeight.value}px` }
})

const streamingScrollInlineStyle = computed(() => {
  if (!useStreamingIntrinsicLayout.value) return {}
  return { maxHeight: `${streamingIntrinsicMaxHeightPx.value}px` }
})

let resizeObserver: ResizeObserver | null = null
let smallCardMeasureObserver: ResizeObserver | null = null
let autoScrollRaf: number | null = null

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

/**
 * 流式未展开且内层已溢出：视口底部停在「可滚动下限之上约一行高」，配合 smooth。
 */
function scheduleAutoScroll() {
  if (!useStreamingIntrinsicLayout.value) return
  if (autoScrollRaf != null) cancelAnimationFrame(autoScrollRaf)
  autoScrollRaf = requestAnimationFrame(() => {
    autoScrollRaf = null
    const el = scrollRef.value
    if (!el) return
    const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
    if (maxScroll <= 0) {
      updateMaskVisibility()
      return
    }
    const lineHeight = getLineHeightPx(el)
    const target = Math.max(0, maxScroll - lineHeight)
    try {
      el.scrollTo({ top: target, behavior: 'smooth' })
    } catch {
      el.scrollTop = target
    }
    requestAnimationFrame(updateMaskVisibility)
  })
}

/** 从展开折回流式未展开 intrinsic 后，待布局稳定再跟滚 */
function scheduleStreamingFollowAfterCollapse() {
  if (!props.isStreaming || isExpanded.value) return
  nextTick(() => {
    requestAnimationFrame(() => {
      scheduleAutoScroll()
      requestAnimationFrame(() => {
        scheduleAutoScroll()
      })
    })
  })
}

function expandedHeightFloorPx(): number {
  return Math.max(props.smallCardHeight, props.streamingWindowHeight)
}

function computeExpandedHeight(): number {
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800
  const maxPx = vh * props.expandedMaxVhRatio
  const el = scrollRef.value
  const contentHeight = el ? el.scrollHeight : expandedHeightFloorPx()
  return Math.max(expandedHeightFloorPx(), Math.min(contentHeight, maxPx))
}

function applyHeightForMode() {
  if (isExpanded.value) {
    nextTick(() => {
      currentHeight.value = computeExpandedHeight()
      nextTick(updateMaskVisibility)
    })
  } else if (!props.isStreaming) {
    currentHeight.value = props.smallCardHeight
  }
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
  () => props.content,
  () => {
    if (props.isStreaming && !isExpanded.value) {
      scheduleAutoScroll()
      nextTick(() => {
        updateMaskVisibility()
      })
    } else if (isExpanded.value) {
      nextTick(() => {
        currentHeight.value = computeExpandedHeight()
        updateMaskVisibility()
      })
    }
  },
)

watch(
  () => props.isStreaming,
  (streaming, prev) => {
    if (!streaming && prev) {
      if (!isExpanded.value) {
        currentHeight.value = props.smallCardHeight
      }
    } else if (streaming && !isExpanded.value) {
      scheduleAutoScroll()
      nextTick(updateMaskVisibility)
    }
  },
)

watch(isExpanded, () => {
  applyHeightForMode()
  if (props.isStreaming && !isExpanded.value) {
    scheduleStreamingFollowAfterCollapse()
  }
})

watch(
  () =>
    [
      props.streamingMaxHeightPx,
      props.smallCardHeight,
      props.expandedMaxVhRatio,
      props.streamingWindowHeight,
    ] as const,
  () => applyHeightForMode(),
)

watch(
  () => [showSmallCard.value, formattedDuration.value] as const,
  async () => {
    if (!showSmallCard.value) {
      teardownSmallCardMeasureObserver()
      collapsedMeasuredWidth.value = null
      return
    }
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
  applyHeightForMode()
  if (props.isStreaming && !isExpanded.value) {
    scheduleAutoScroll()
    nextTick(updateMaskVisibility)
  }
  if (typeof ResizeObserver !== 'undefined' && scrollRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (isExpanded.value) {
        currentHeight.value = computeExpandedHeight()
      }
      updateMaskVisibility()
    })
    resizeObserver.observe(scrollRef.value)
  }
  window.addEventListener('resize', onWindowResize)
})

onBeforeUnmount(() => {
  if (autoScrollRaf != null) cancelAnimationFrame(autoScrollRaf)
  resizeObserver?.disconnect()
  resizeObserver = null
  teardownSmallCardMeasureObserver()
  window.removeEventListener('resize', onWindowResize)
})

function onWindowResize() {
  if (isExpanded.value) currentHeight.value = computeExpandedHeight()
  if (showSmallCard.value) measureCollapsedSmallCardWidth()
  updateMaskVisibility()
}
</script>

<template>
  <div
    class="reasoning-bubble reasoning-bubble-surface rounded-lg text-xs leading-relaxed relative overflow-hidden"
    :class="[rootLayoutClass, showSmallCard ? 'cursor-pointer' : (isExpanded ? '' : 'cursor-pointer')]"
    :style="rootInlineStyle"
    @click="onRootClick"
  >
    <div
      v-if="showSmallCard"
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

    <div
      class="reasoning-scroll overflow-y-auto overflow-x-hidden pl-3 pr-8 py-2.5 whitespace-pre-wrap break-words transition-opacity duration-200"
      :class="[
        useStreamingIntrinsicLayout ? 'relative min-h-0 reasoning-scroll--streaming-intrinsic' : 'absolute inset-0',
        showSmallCard ? 'opacity-0 pointer-events-none' : 'opacity-100',
      ]"
      :style="streamingScrollInlineStyle"
      ref="scrollRef"
      @scroll="updateMaskVisibility"
    >
      <div class="reasoning-text">{{ content }}</div>
      <div class="reasoning-tail-padding" aria-hidden="true" />
    </div>

    <div
      class="reasoning-small-card absolute inset-0 flex items-center gap-1 whitespace-nowrap pl-2 pr-7 transition-opacity duration-200"
      :class="showSmallCard ? 'opacity-100' : 'opacity-0 pointer-events-none'"
      :aria-hidden="!showSmallCard"
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
      v-if="!showSmallCard"
      class="reasoning-mask reasoning-mask-top"
      :class="topMaskVisible ? 'opacity-100' : 'opacity-0'"
      aria-hidden="true"
    />
    <div
      v-if="!showSmallCard"
      class="reasoning-mask reasoning-mask-bottom"
      :class="bottomMaskVisible ? 'opacity-100' : 'opacity-0'"
      aria-hidden="true"
    />

    <button
      type="button"
      class="reasoning-toggle-icon absolute z-10 flex items-center justify-center rounded hover:bg-white/10 transition-all duration-200"
      :class="[
        isExpanded ? 'rotate-90' : '',
        showSmallCard ? 'right-1 top-1/2 h-5 w-5 -translate-y-1/2' : 'top-2 right-2 h-6 w-6',
      ]"
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
  transition:
    height 320ms cubic-bezier(0.4, 0, 0.2, 1),
    width 320ms cubic-bezier(0.4, 0, 0.2, 1);
  will-change: height, width;
}
.reasoning-scroll {
  scroll-behavior: smooth;
}
.reasoning-scroll--streaming-intrinsic {
  scroll-behavior: auto;
}
.reasoning-scroll::-webkit-scrollbar {
  width: 4px;
}
.reasoning-scroll::-webkit-scrollbar-thumb {
  background-color: color-mix(in srgb, var(--color-text-muted, #9ca3af) 24%, transparent);
  border-radius: 4px;
}
.reasoning-tail-padding {
  height: 1.5em;
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
  background: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--color-reasoning-bubble-bg, rgba(30, 30, 30, 0.5)) 100%, transparent) 0%,
    color-mix(in srgb, var(--color-reasoning-bubble-bg, rgba(30, 30, 30, 0.5)) 85%, transparent) 40%,
    transparent 100%
  );
  box-shadow: inset 0 10px 14px -10px color-mix(in srgb, var(--color-primary, #6366f1) 32%, transparent);
}
.reasoning-mask-bottom {
  bottom: 0;
  height: 32px;
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--color-reasoning-bubble-bg, rgba(30, 30, 30, 0.5)) 100%, transparent) 0%,
    color-mix(in srgb, var(--color-reasoning-bubble-bg, rgba(30, 30, 30, 0.5)) 85%, transparent) 45%,
    transparent 100%
  );
  box-shadow: inset 0 -10px 14px -10px color-mix(in srgb, var(--color-primary, #6366f1) 32%, transparent);
}
</style>
