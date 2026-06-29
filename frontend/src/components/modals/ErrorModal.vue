<script setup lang="ts">
import { ref } from 'vue'
import { X, Copy, Check } from 'lucide-vue-next'
import type { ErrorStackItem } from '../../composables/useErrorStack'

const props = defineProps<{
  item: ErrorStackItem
  offsetY: number
  zIndex: number
}>()

const emit = defineEmits<{
  (e: 'close', id: string): void
  (e: 'pause', id: string): void
  (e: 'resume', id: string): void
}>()

const copied = ref(false)

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.item.message)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1200)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <div
    class="fixed right-4 w-[min(560px,calc(100vw-2rem))] pointer-events-auto"
    :style="{ bottom: `${16 + offsetY}px`, zIndex }"
    @mouseenter="emit('pause', item.id)"
    @mouseleave="emit('resume', item.id)"
  >
    <div class="surface-panel overflow-hidden border-[color-mix(in_srgb,var(--color-error)_30%,transparent)] bg-[var(--color-error-bg)]">
      <div class="flex items-center justify-between px-3 py-2 border-b border-[color-mix(in_srgb,var(--color-error)_20%,transparent)]">
        <div class="text-sm font-semibold text-[var(--color-error-text)]">{{ item.title }}</div>
        <button type="button" class="icon-button p-1 text-[var(--color-error-text)]" aria-label="关闭错误提示" @click="emit('close', item.id)">
          <X class="w-4 h-4" />
        </button>
      </div>
      <div class="px-3 py-2">
        <pre class="text-xs leading-5 text-[var(--color-error-text)] whitespace-pre-wrap break-words max-h-44 overflow-auto">{{ item.message }}</pre>
      </div>
      <div class="px-3 pb-3 flex justify-end">
        <button class="btn btn-xs btn-secondary" @click="copyMessage">
          <Check v-if="copied" class="w-3 h-3" />
          <Copy v-else class="w-3 h-3" />
          {{ copied ? '已复制' : '复制错误' }}
        </button>
      </div>
    </div>
  </div>
</template>
