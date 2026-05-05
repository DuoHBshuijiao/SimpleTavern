<template>
  <div
    v-if="capsules.length > 0"
    class="group relative z-20 flex w-full shrink-0 items-center gap-2 overflow-x-auto px-[18px] py-1.5 scrollbar-none"
  >
    <span
      v-for="(cap, i) in visibleCapsules"
      :key="i"
      class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.45] transition-colors duration-300 shrink-0 select-none"
      :class="[
        cap.flashing
          ? 'border-[var(--color-brand-a50)] bg-[var(--color-brand-a30)]'
          : 'border-[var(--color-border)]/80 bg-surface-overlay'
      ]"
    >
      <span class="text-[var(--color-text-muted)] text-xs leading-4">{{ cap.field }}</span>
      <span class="text-[var(--color-text)] text-xs leading-4 font-medium">{{ cap.value }}</span>
    </span>

    <!-- MVU 运行指示器 -->
    <span
      v-if="isRunning"
      class="inline-flex items-center justify-center w-4 h-4 shrink-0"
      aria-hidden="true"
    >
      <span class="block w-3.5 h-3.5 rounded-full border-2 border-[var(--color-text-muted)] border-t-transparent animate-spin" />
    </span>

    <!-- 面板开关 -->
    <button
      type="button"
      class="inline-flex items-center justify-center w-5 h-5 rounded-md shrink-0 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-opacity transition-colors ml-0.5"
      :class="preferHoverChrome ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'"
      aria-label="MVU 工作日志"
      @click="$emit('toggle-panel')"
    >
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePreferHoverChrome } from '../../composables/usePreferHoverChrome'
import type { CapsuleItem } from '../../stores/mvu'

const { preferHoverChrome } = usePreferHoverChrome()

const props = withDefaults(defineProps<{
  capsules: CapsuleItem[]
  isRunning: boolean
  maxVisible?: number
}>(), {
  maxVisible: 5,
})

defineEmits<{
  'toggle-panel': []
}>()

const visibleCapsules = computed(() => props.capsules.slice(0, props.maxVisible))
</script>
