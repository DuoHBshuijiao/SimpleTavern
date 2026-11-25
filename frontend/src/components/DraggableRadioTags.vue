<script setup lang="ts" generic="Value extends string">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import ThemedRadioTags from './ThemedRadioTags.vue'

const props = defineProps<{
  modelValue: Value
  options: { value: Value; label: string; ariaLabel?: string }[]
  ariaLabel: string
  stretch?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Value] }>()

type ThumbPosition = { left: number; top: number; width: number; height: number }
const root = ref<HTMLElement | null>(null)
const thumb = ref<HTMLElement | null>(null)
const preview = shallowRef<Value | null>(null)
const selectedPosition = shallowRef<ThumbPosition | null>(null)
const dragPosition = shallowRef<ThumbPosition | null>(null)
const position = computed(() => dragPosition.value ?? selectedPosition.value)
let drag: { pointerId: number; startX: number; startCenter: number; scaleX: number; startValue: Value; moved: boolean } | null = null
let suppressClick = false
let resizeObserver: ResizeObserver | undefined

function cancelDrag() {
  drag = null
  dragPosition.value = null
  preview.value = null
}

function buttons() {
  return Array.from(root.value?.querySelectorAll<HTMLButtonElement>('button[role="radio"]') ?? [])
}

function getTrackBounds() {
  if (!root.value) return null
  const bounds = root.value.getBoundingClientRect()
  if (!bounds.width || !bounds.height) return null
  const style = getComputedStyle(root.value)
  // 弹窗入场会缩放，胶囊仍使用分段控件自身的布局坐标。
  return { bounds, scaleX: bounds.width / parseFloat(style.width), scaleY: bounds.height / parseFloat(style.height) }
}

function getStops() {
  const track = getTrackBounds()
  if (!track) return []
  const { bounds, scaleX, scaleY } = track
  return buttons().flatMap((button, index) => {
    const option = props.options[index]
    if (!option || button.disabled) return []
    const rect = button.getBoundingClientRect()
    const left = (rect.left - bounds.left) / scaleX
    const width = rect.width / scaleX
    return [{
      value: option.value, button, center: left + width / 2,
      position: { left, top: (rect.top - bounds.top) / scaleY, width, height: rect.height / scaleY },
    }]
  })
}

function measureSelection() {
  selectedPosition.value = getStops().find(stop => stop.value === props.modelValue)?.position ?? null
}

function observeButtons() {
  resizeObserver?.disconnect()
  if (root.value) resizeObserver?.observe(root.value)
  for (const button of buttons()) resizeObserver?.observe(button)
  measureSelection()
}

onMounted(() => {
  resizeObserver = new ResizeObserver(measureSelection)
  observeButtons()
})
onBeforeUnmount(() => resizeObserver?.disconnect())

watch(() => props.modelValue, measureSelection, { flush: 'post' })
watch(() => props.options.map(option => option.value).join(','), () => {
  cancelDrag()
  observeButtons()
}, { flush: 'post' })

function startDrag(event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0) return
  suppressClick = false
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[aria-checked="true"]')
  if (!button || button.disabled || props.options.length < 2 || !thumb.value || !selectedPosition.value) return
  const track = getTrackBounds()
  if (!track) return
  const { bounds, scaleX, scaleY } = track
  const rect = thumb.value.getBoundingClientRect()
  const { width, height } = selectedPosition.value
  // 连续点击后立即按住时，从胶囊正在显示的位置接手。
  const startCenter = (rect.left + rect.width / 2 - bounds.left) / scaleX
  drag = { pointerId: event.pointerId, startX: event.clientX, startCenter, scaleX, startValue: props.modelValue, moved: false }
  dragPosition.value = {
    left: startCenter - width / 2, top: (rect.top + rect.height / 2 - bounds.top) / scaleY - height / 2, width, height,
  }
  button.setPointerCapture(event.pointerId)
}

function getStop(center: number) {
  const stops = getStops()
  const first = stops[0]
  const last = stops[stops.length - 1]
  if (!first || !last) return null
  const clamped = Math.max(first.center, Math.min(last.center, center))
  const closest = stops.reduce((best, stop) => Math.abs(stop.center - clamped) < Math.abs(best.center - clamped) ? stop : best, first)
  return { ...closest, clamped }
}

function moveDrag(event: PointerEvent) {
  if (!drag || !dragPosition.value || drag.pointerId !== event.pointerId) return
  const delta = event.clientX - drag.startX
  if (Math.abs(delta) > 2) drag.moved = true
  if (!drag.moved) return
  const target = getStop(drag.startCenter + delta / drag.scaleX)
  if (!target) return
  dragPosition.value = { ...dragPosition.value, left: target.clamped - dragPosition.value.width / 2 }
  preview.value = target.value
}

function finishDrag(event: PointerEvent) {
  if (!drag || drag.pointerId !== event.pointerId) return
  const finished = drag
  cancelDrag()
  if (!finished.moved) return
  // 抬起指针后，浏览器还会向最初捕获指针的按钮派发 click。
  suppressClick = true
  const target = getStop(finished.startCenter + (event.clientX - finished.startX) / finished.scaleX)
  if (!target || target.value === finished.startValue) return
  target.button.focus({ preventScroll: true })
  emit('update:modelValue', target.value)
}

function ignoreDragClick(event: MouseEvent) {
  if (!suppressClick || event.detail === 0) return
  suppressClick = false
  event.stopPropagation()
}
</script>

<template>
  <div ref="root" class="relative">
    <span
      v-if="position"
      ref="thumb"
      class="radio-tags-drag-thumb border border-brand bg-brand/15 light:border-transparent"
      :class="{ 'radio-tags-drag-thumb--pressed': dragPosition }"
      aria-hidden="true"
      :style="{
        translate: `${position.left}px ${position.top}px`,
        width: `${position.width}px`,
        height: `${position.height}px`,
        scale: dragPosition ? `${1 - 2.5 / position.width} ${1 - 2.5 / position.height}` : '1',
      }"
    />
    <ThemedRadioTags
      class="draggable-radio-tags"
      :class="{ 'draggable-radio-tags--has-thumb': position, 'draggable-radio-tags--dragging': dragPosition }"
      :model-value="preview ?? modelValue"
      :options="options"
      :ariaLabel="ariaLabel"
      :stretch="stretch"
      @update:model-value="emit('update:modelValue', $event)"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="finishDrag"
      @pointercancel="cancelDrag"
      @lostpointercapture="cancelDrag"
      @click.capture="ignoreDragClick"
    />
  </div>
</template>

<style scoped>
.draggable-radio-tags {
  touch-action: pan-y;
  user-select: none;
}
.draggable-radio-tags--dragging {
  cursor: pointer;
}
.draggable-radio-tags--has-thumb :deep(button) {
  position: relative;
}
.draggable-radio-tags--has-thumb :deep(button[aria-checked='true']),
.draggable-radio-tags--dragging :deep(button) {
  background: transparent;
  border-color: transparent;
}
.radio-tags-drag-thumb {
  position: absolute;
  inset: 0 auto auto 0;
  z-index: 0;
  pointer-events: none;
  border-radius: var(--radius-lg);
  transition: translate var(--transition-normal), width var(--transition-normal), height var(--transition-normal),
    scale var(--transition-fast);
}
.radio-tags-drag-thumb--pressed {
  transition-property: scale;
}
@media (prefers-reduced-motion: reduce) {
  .radio-tags-drag-thumb,
  .draggable-radio-tags :deep(button) {
    transition: none;
  }
}
</style>
