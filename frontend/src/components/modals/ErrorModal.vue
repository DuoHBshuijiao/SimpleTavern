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
    <div
      class="rounded-xl border border-red-400/30 bg-red-500/10 shadow-lg overflow-hidden"
      style="backdrop-filter: blur(var(--blur-light)); -webkit-backdrop-filter: blur(var(--blur-light));"
    >
      <div class="flex items-center justify-between px-3 py-2 border-b border-red-400/20">
        <div class="text-sm font-semibold text-red-200">{{ item.title }}</div>
        <button class="p-1 rounded text-red-200/80 hover:text-red-100 hover:bg-white/10 transition-colors" @click="emit('close', item.id)">
          <X class="w-4 h-4" />
        </button>
      </div>
      <div class="px-3 py-2">
        <pre class="text-xs leading-5 text-red-100/95 whitespace-pre-wrap break-words max-h-44 overflow-auto">{{ item.message }}</pre>
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
