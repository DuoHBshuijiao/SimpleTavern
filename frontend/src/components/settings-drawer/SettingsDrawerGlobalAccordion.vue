<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next'

defineProps<{
  title: string
  /** 内容区额外 class，如 space-y-5 */
  contentClass?: string
}>()

const open = defineModel<boolean>('open', { required: true })
</script>

<template>
  <div class="overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-panel-bg)]">
    <button
      type="button"
      class="flex w-full cursor-pointer select-none items-center justify-between gap-3 px-4 py-3.5 text-left text-sm text-[var(--color-text-secondary)] hover:bg-surface-hover/40"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span>{{ title }}</span>
      <ChevronDown
        class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[800ms] ease-in-out"
        :class="open ? 'rotate-180' : ''"
      />
    </button>
    <div
      class="grid transition-[grid-template-rows] duration-[800ms] ease-in-out"
      :class="open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
    >
      <div class="min-h-0 overflow-hidden">
        <div
          class="border-t border-[var(--color-border-subtle)] px-4 pb-4 pt-4"
          :class="contentClass ?? 'space-y-3'"
        >
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>
