<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    disabled?: boolean
    placeholder?: string
    /** 1-based 逻辑行号，命中行将使用错误背景高亮 */
    errorLines?: number[]
    /** 滚动区额外类名（如 min-h-[12rem]）；默认不强制 min-h-60vh，避免矮窗口撑破布局 */
    minHeightClass?: string
  }>(),
  {
    disabled: false,
    placeholder: '',
    errorLines: () => [],
    minHeightClass: '',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const shellRef = ref<HTMLElement | null>(null)
/** 唯一纵向滚动容器：行号与 textarea 同层随其滚动，避免双通道 translate 累积误差 */
const scrollHostRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const mirrorInnerRef = ref<HTMLElement | null>(null)
const textareaScrollHeight = ref(0)
/** 与 scrollHost scrollHeight 同步，行号区全高背景（inset-0 在 flex 流中易被内容高度限制为视口） */
const gutterBackdropHeightPx = ref(0)
const lineHeightPx = ref(18)
const textareaFontFamily = ref('monospace')
const textareaFontSize = ref('12px')
const textareaFontWeight = ref('400')
const textareaFontStyle = ref('normal')
const textareaLetterSpacing = ref('normal')
/** 每个逻辑行在镜像层中的真实像素高度（与 textarea 换行一致） */
const lineHeights = ref<number[]>([])
const paddingTopPx = ref(8)
const paddingBottomPx = ref(8)

let ro: ResizeObserver | null = null

const logicalLines = computed(() => props.modelValue.split(/\n/))

const errorLineSet = computed(() => new Set(props.errorLines ?? []))

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

/** 无内部滚动：高度铺满内容，由外层 scrollHost 统一滚动 */
function syncTextareaHeight() {
  const ta = textareaRef.value
  if (!ta) return
  ta.style.height = 'auto'
  const h = ta.scrollHeight
  ta.style.height = `${h}px`
  textareaScrollHeight.value = h
}

function measureLineHeightPxFromTextarea(ta: HTMLTextAreaElement): number {
  const cs = getComputedStyle(ta)
  const d = document.createElement('div')
  d.style.cssText =
    'position:absolute;visibility:hidden;left:-99999px;top:0;white-space:pre;margin:0;padding:0;border:none;box-sizing:border-box;'
  d.style.fontFamily = cs.fontFamily
  d.style.fontSize = cs.fontSize
  d.style.fontWeight = cs.fontWeight
  d.style.fontStyle = cs.fontStyle
  d.style.lineHeight = cs.lineHeight
  d.style.letterSpacing = cs.letterSpacing
  d.textContent = 'M'
  document.body.appendChild(d)
  const h = d.offsetHeight
  document.body.removeChild(d)
  return Math.max(1, h)
}

function readTextareaMetrics() {
  const ta = textareaRef.value
  if (!ta) return
  const cs = getComputedStyle(ta)
  textareaFontFamily.value = cs.fontFamily
  textareaFontSize.value = cs.fontSize
  textareaFontWeight.value = cs.fontWeight
  textareaFontStyle.value = cs.fontStyle
  textareaLetterSpacing.value = cs.letterSpacing || 'normal'
  lineHeightPx.value = measureLineHeightPxFromTextarea(ta)
  paddingTopPx.value = parseFloat(cs.paddingTop) || 0
  paddingBottomPx.value = parseFloat(cs.paddingBottom) || 0
}

/**
 * 从与 textarea 同宽、同排版约束的镜像层读取每个逻辑行的真实高度，
 * 使行号列与软换行后的文本一一对应，避免离屏估算误差。
 */
function measureLineHeightsFromMirror() {
  const root = mirrorInnerRef.value
  const ta = textareaRef.value
  if (!root || !ta) return
  readTextareaMetrics()
  const lines = logicalLines.value
  const els = root.querySelectorAll('[data-mirror-line]')
  const lh = lineHeightPx.value
  const heights: number[] = []
  for (let i = 0; i < lines.length; i++) {
    const el = els[i] as HTMLElement | undefined
    if (el) {
      const h = el.getBoundingClientRect().height
      heights.push(Math.max(1, h))
    } else {
      heights.push(lh)
    }
  }
  /** 与 textarea 内容区总高度对齐，消除 offset/取整导致的逐行累积偏差 */
  const padT = paddingTopPx.value
  const padB = paddingBottomPx.value
  const innerTarget = Math.max(0, ta.scrollHeight - padT - padB)
  let sum = heights.reduce((a, b) => a + b, 0)
  if (lines.length > 0 && sum > 0 && Math.abs(innerTarget - sum) > 0.25) {
    const add = (innerTarget - sum) / lines.length
    for (let i = 0; i < heights.length; i++) {
      const cur = heights[i] ?? lh
      heights[i] = Math.max(0.5, cur + add)
    }
  }
  lineHeights.value = heights
  textareaScrollHeight.value = ta.scrollHeight
}

function scheduleRemeasure() {
  void nextTick(() => {
    syncTextareaHeight()
    void nextTick(() => {
      requestAnimationFrame(() => {
        measureLineHeightsFromMirror()
        const host = scrollHostRef.value
        gutterBackdropHeightPx.value = Math.max(
          host?.scrollHeight ?? 0,
          textareaScrollHeight.value,
        )
      })
    })
  })
}

const highlightBlocks = computed(() => {
  const lines = logicalLines.value
  const heights = lineHeights.value
  const lh = lineHeightPx.value
  const padT = paddingTopPx.value
  const blocks: { top: number; height: number; error: boolean }[] = []
  let y = padT
  for (let i = 0; i < lines.length; i++) {
    const h = heights[i] ?? lh
    blocks.push({
      top: y,
      height: h,
      error: errorLineSet.value.has(i + 1),
    })
    y += h
  }
  return blocks
})

function gutterRowHeight(i: number): number {
  return lineHeights.value[i] ?? lineHeightPx.value
}

watch(
  () => props.modelValue,
  () => scheduleRemeasure(),
  { flush: 'post' },
)

watch(
  () => [...(props.errorLines ?? [])],
  () => {
    /* 仅重绘高亮 */
  },
)

onMounted(() => {
  void nextTick(() => {
    readTextareaMetrics()
    syncTextareaHeight()
    scheduleRemeasure()
  })
  const ta = textareaRef.value
  const shell = shellRef.value
  const host = scrollHostRef.value
  if (ta && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => {
      scheduleRemeasure()
    })
    ro.observe(ta)
    if (shell) ro.observe(shell)
    if (host) ro.observe(host)
  }
  window.addEventListener('resize', scheduleRemeasure)
})

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  window.removeEventListener('resize', scheduleRemeasure)
})

/** 将 1-based 逻辑行滚入视口（滚动统一容器 scrollHost） */
function scrollToLogicalLine(line1: number) {
  const host = scrollHostRef.value
  const ta = textareaRef.value
  if (!host || !ta || line1 < 1) return
  const idx = line1 - 1
  const lines = logicalLines.value
  const heights = lineHeights.value
  const lh = lineHeightPx.value
  const padT = paddingTopPx.value
  let y = padT
  for (let i = 0; i < idx && i < lines.length; i++) {
    y += heights[i] ?? lh
  }
  host.scrollTop = Math.max(0, y - host.clientHeight * 0.25)
  ta.focus()
}

defineExpose({ scrollToLogicalLine })
</script>

<template>
  <div
    ref="shellRef"
    class="wgsl-monospace-editor flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border-default)] bg-[var(--color-dark-surface)] transition-colors focus-within:border-[var(--color-brand)] focus-within:shadow-[0_0_0_3px_var(--color-brand-a15)]"
  >
    <div
      ref="scrollHostRef"
      class="relative flex min-h-0 w-full min-w-0 max-h-full flex-1 flex-row items-start overflow-y-auto overflow-x-hidden resize-y"
      :class="minHeightClass"
    >
      <div
        class="pointer-events-none absolute left-0 top-0 z-0 w-[3.25rem] rounded-l-lg border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]"
        :style="{ height: `${gutterBackdropHeightPx}px` }"
        aria-hidden="true"
      />
      <!-- 行号列：背景用上层全高条；行高仍由镜像测量，不改动对齐逻辑 -->
      <div
        class="relative z-[1] flex min-h-0 w-[3.25rem] shrink-0 select-none flex-col bg-transparent text-[var(--color-text-muted)]"
      >
        <div
          class="flex min-h-0 min-w-0 flex-col px-1.5"
          :style="{
            paddingTop: `${paddingTopPx}px`,
            paddingBottom: `${paddingBottomPx}px`,
            boxSizing: 'border-box',
          }"
        >
          <div
            v-for="(_, i) in logicalLines"
            :key="i"
            class="tabular-nums flex items-start justify-end"
            :style="{
              boxSizing: 'border-box',
              height: `${gutterRowHeight(i)}px`,
              minHeight: `${gutterRowHeight(i)}px`,
              lineHeight: `${lineHeightPx}px`,
              fontFamily: textareaFontFamily,
              fontSize: textareaFontSize,
              fontWeight: textareaFontWeight,
              fontStyle: textareaFontStyle,
              letterSpacing: textareaLetterSpacing,
            }"
          >
            {{ i + 1 }}
          </div>
        </div>
      </div>

      <div class="relative min-h-0 min-w-0 flex-1">
        <!-- 镜像层：与 textarea 同 padding/字体/断行规则，用于测量每逻辑行真实高度（不可见、不拦截事件） -->
        <div
          class="pointer-events-none absolute left-0 right-0 top-0 z-0 overflow-visible"
          aria-hidden="true"
          style="visibility: hidden"
        >
          <div
            ref="mirrorInnerRef"
            class="box-border w-full px-3 py-2 font-mono text-[length:var(--text-xs)] leading-relaxed tab-[4] whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
          >
            <div
              v-for="(line, i) in logicalLines"
              :key="i"
              data-mirror-line
              class="whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
            >
              {{ line.length === 0 ? '\u00a0' : line }}
            </div>
          </div>
        </div>

        <div
          class="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-r-lg"
          aria-hidden="true"
        >
          <div
            class="relative w-full"
            :style="{
              height: `${textareaScrollHeight || 0}px`,
            }"
          >
            <div
              v-for="(b, bi) in highlightBlocks"
              :key="bi"
              class="absolute left-0 right-0"
              :class="b.error ? 'bg-[var(--color-error-bg)]' : ''"
              :style="{
                top: `${b.top}px`,
                height: `${b.height}px`,
              }"
            />
          </div>
        </div>
        <textarea
          ref="textareaRef"
          :value="modelValue"
          class="relative z-[1] box-border w-full min-h-0 resize-none overflow-hidden border-0 bg-transparent px-3 py-2 font-mono text-[length:var(--text-xs)] leading-relaxed tab-[4] whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="disabled"
          :placeholder="placeholder"
          spellcheck="false"
          autocapitalize="off"
          autocomplete="off"
          @input="onInput"
        />
      </div>
    </div>
  </div>
</template>
