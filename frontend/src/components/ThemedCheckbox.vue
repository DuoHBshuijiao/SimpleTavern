<script setup lang="ts">
import { Check } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  checked: boolean
  disabled?: boolean
  ariaLabel?: string
}>(), {
  disabled: false,
  ariaLabel: '切换选项',
})

const emit = defineEmits<{
  (e: 'update:checked', value: boolean): void
}>()

function toggle() {
  if (props.disabled) return
  emit('update:checked', !props.checked)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== ' ' && event.key !== 'Enter') return
  event.preventDefault()
  toggle()
}
</script>

<template>
  <button
    type="button"
    role="checkbox"
    :aria-checked="checked"
    :aria-label="ariaLabel"
    :disabled="disabled"
    class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-focus-ring)] disabled:cursor-not-allowed disabled:opacity-50"
    :class="checked ? 'border-brand bg-brand text-[var(--color-on-brand)]' : 'border-[var(--color-border)] bg-surface-overlay text-transparent'"
    @click="toggle"
    @keydown="onKeydown"
  >
    <Check class="h-3 w-3" />
  </button>
</template>