<script setup lang="ts">
import { computed } from 'vue'

type RadioTagOption = {
  label: string
  value: string
  disabled?: boolean
}

const props = withDefaults(defineProps<{
  modelValue: string
  options: RadioTagOption[]
  ariaLabel?: string
  disabled?: boolean
}>(), {
  ariaLabel: '选项',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const activeIndex = computed(() => props.options.findIndex((item) => item.value === props.modelValue))

function selectValue(value: string) {
  if (props.disabled) return
  const target = props.options.find((item) => item.value === value)
  if (!target || target.disabled) return
  emit('update:modelValue', value)
}

function onOptionKeydown(event: KeyboardEvent, index: number) {
  if (props.disabled) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight' && event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
  event.preventDefault()

  const direction = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1
  const len = props.options.length
  if (!len) return

  let nextIndex = index
  for (let i = 0; i < len; i += 1) {
    nextIndex = (nextIndex + direction + len) % len
    const candidate = props.options[nextIndex]
    if (candidate && !candidate.disabled) {
      selectValue(candidate.value)
      return
    }
  }
}
</script>

<template>
  <div
    class="inline-flex items-center gap-1 rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay p-1"
    role="radiogroup"
    :aria-label="ariaLabel"
    :aria-disabled="disabled ? 'true' : 'false'"
  >
    <button
      v-for="(item, idx) in options"
      :key="item.value"
      type="button"
      role="radio"
      :aria-checked="modelValue === item.value"
      :disabled="disabled || item.disabled"
      class="inline-flex min-h-7 items-center rounded-lg px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60 disabled:cursor-not-allowed disabled:opacity-50"
      :class="modelValue === item.value
        ? 'border border-brand bg-brand/15 text-[var(--color-text)]'
        : 'border border-transparent text-[var(--color-text-secondary)] hover:bg-surface-muted hover:text-[var(--color-text)]'"
      :tabindex="modelValue === item.value || (activeIndex === -1 && idx === 0) ? 0 : -1"
      @click="selectValue(item.value)"
      @keydown="onOptionKeydown($event, idx)"
    >
      {{ item.label }}
    </button>
  </div>
</template>
