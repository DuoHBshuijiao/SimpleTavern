<script setup lang="ts" generic="Value extends string">
import { computed } from 'vue'

type RadioTagOption = {
  label: string
  value: Value
  disabled?: boolean
  ariaLabel?: string
}

const props = withDefaults(defineProps<{
  modelValue: Value
  options: RadioTagOption[]
  ariaLabel?: string
  disabled?: boolean
  stretch?: boolean
}>(), {
  ariaLabel: '选项',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: Value): void
}>()

const focusIndex = computed(() => {
  const active = props.options.findIndex(item => item.value === props.modelValue && !item.disabled)
  return active >= 0 ? active : props.options.findIndex(item => !item.disabled)
})

function selectValue(value: Value) {
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
      const group = (event.currentTarget as HTMLElement).parentElement
      group?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[nextIndex]?.focus()
      return
    }
  }
}
</script>

<template>
  <div
    class="inline-flex items-center gap-1 rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay p-1"
    :class="{ 'w-full': stretch }"
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
      :aria-label="item.ariaLabel"
      :disabled="disabled || item.disabled"
      class="inline-flex min-h-7 items-center rounded-lg text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      :class="[stretch ? 'min-w-0 flex-1 justify-center px-1 text-center' : 'px-2.5', modelValue === item.value
        ? 'border border-brand light:border-transparent bg-brand/15 text-[var(--color-text)]'
        : 'border border-transparent text-[var(--color-text-secondary)] hover:bg-surface-muted hover:text-[var(--color-text)]']"
      :tabindex="idx === focusIndex ? 0 : -1"
      @click="selectValue(item.value)"
      @keydown="onOptionKeydown($event, idx)"
    >
      {{ item.label }}
    </button>
  </div>
</template>
