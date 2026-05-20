<script setup lang="ts">
import type { ForkLineageResponse } from '../../types/models'

defineProps<{
  lineage: ForkLineageResponse | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'navigate-source': []
}>()
</script>

<template>
  <div
    v-if="lineage?.origin"
    class="mx-4 mb-2 px-3 py-2 rounded-lg border border-brand-a20 bg-brand-a10 text-sm text-[var(--color-text-secondary)]"
  >
    <span v-if="loading" class="text-[var(--color-text-muted)]">加载分叉信息…</span>
    <template v-else>
      <span>分叉自</span>
      <button
        type="button"
        class="text-brand hover:underline mx-0.5"
        aria-label="跳转到源会话"
        @click="emit('navigate-source')"
      >
        「{{ lineage.origin.title }}」
      </button>
      <span>的第 {{ lineage.origin.messageIndex }} 条消息</span>
    </template>
  </div>
</template>
