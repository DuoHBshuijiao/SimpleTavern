<script setup lang="ts">
import { ref, watch } from 'vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import type { ReasoningEffort } from '../../types/models'

const props = defineProps<{
  modelValue: ReasoningEffort
  options: { value: ReasoningEffort; label: string; ariaLabel: string }[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: ReasoningEffort] }>()

const preview = ref<ReasoningEffort | null>(null)
const grip = ref<{ left: number; top: number; width: number; height: number; shift: number } | null>(null)
let drag: { pointerId: number; startX: number; startCenter: number; startValue: ReasoningEffort; moved: boolean } | null = null
let suppressClick = false

function cancelDrag() {
  drag = null
  grip.value = null
  preview.value = null
}

watch(() => props.options.map(option => option.value).join(','), cancelDrag)

function startDrag(event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0) return
  suppressClick = false
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[aria-checked="true"]')
  if (!button || button.disabled || props.options.length < 2) return
  const group = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const rect = button.getBoundingClientRect()
  drag = { pointerId: event.pointerId, startX: event.clientX, startCenter: rect.left + rect.width / 2,
    startValue: props.modelValue, moved: false }
  grip.value = { left: rect.left - group.left, top: rect.top - group.top, width: rect.width, height: rect.height, shift: 0 }
  button.setPointerCapture(event.pointerId)
}

function getStop(event: PointerEvent, center: number) {
  const group = event.currentTarget as HTMLElement
  const stops = Array.from(group.querySelectorAll<HTMLButtonElement>('button[role="radio"]')).flatMap((button, index) => {
    const option = props.options[index]
    if (!option || button.disabled) return []
    const rect = button.getBoundingClientRect()
    return [{ value: option.value, button, center: rect.left + rect.width / 2 }]
  })
  const first = stops[0]
  const last = stops[stops.length - 1]
  if (!first || !last) return null
  const clamped = Math.max(first.center, Math.min(last.center, center))
  const closest = stops.reduce((best, stop) => Math.abs(stop.center - clamped) < Math.abs(best.center - clamped) ? stop : best, first)
  return { ...closest, clamped }
}

function moveDrag(event: PointerEvent) {
  if (!drag || !grip.value || drag.pointerId !== event.pointerId) return
  const delta = event.clientX - drag.startX
  if (Math.abs(delta) > 2) drag.moved = true
  const target = getStop(event, drag.startCenter + delta)
  if (!target) return
  grip.value.shift = target.clamped - drag.startCenter
  if (drag.moved) preview.value = target.value
}

function finishDrag(event: PointerEvent) {
  if (!drag || drag.pointerId !== event.pointerId) return
  const finished = drag
  cancelDrag()
  if (!finished.moved) return
  // 抬起指针后，浏览器还会向最初捕获指针的按钮派发 click。
  suppressClick = true
  const target = getStop(event, finished.startCenter + event.clientX - finished.startX)
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
  <div class="relative">
    <span
      v-if="grip"
      class="model-control-effort-grip"
      aria-hidden="true"
      :style="{
        left: `${grip.left + 1.25}px`,
        top: `${grip.top + 1.25}px`,
        width: `${grip.width - 2.5}px`,
        height: `${grip.height - 2.5}px`,
        transform: `translateX(${grip.shift}px)`,
      }"
    />
    <ThemedRadioTags
      class="model-control-segment"
      :class="{ 'model-control-segment--dragging': grip }"
      :model-value="preview ?? modelValue"
      :options="options"
      aria-label="思考深度"
      stretch
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
.model-control-segment {
  touch-action: pan-y;
  user-select: none;
}
.model-control-segment :deep(button[aria-checked='true']) {
  cursor: grab;
}
.model-control-segment--dragging :deep(button) {
  position: relative;
  background: transparent;
  border-color: transparent;
  cursor: grabbing;
}
.model-control-effort-grip {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border: 1px solid var(--color-brand);
  border-radius: var(--radius-lg);
  background: color-mix(in oklab, var(--color-brand) 15%, transparent);
}
:global(:root[data-color-scheme='light']) .model-control-effort-grip {
  border-color: transparent;
}
@media (prefers-reduced-motion: reduce) {
  .model-control-segment :deep(button) {
    transition: none;
  }
}
</style>
