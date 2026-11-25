<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'

defineProps<{
  scope: 'chat' | 'workspace'
  hasModel: boolean
}>()

defineEmits<{ 'select-model': [event: MouseEvent] }>()
</script>

<template>
  <div class="assistant-empty-state flex flex-col items-center gap-3 px-3 py-8 text-center"
    :class="{ 'assistant-empty-state--workspace': scope === 'workspace' }">
    <div v-if="scope === 'workspace'" class="assistant-empty-icon flex size-12 items-center justify-center rounded-full bg-brand/10 text-brand">
      <Sparkles class="size-6" aria-hidden="true" />
    </div>
    <p class="text-xs text-[var(--color-text-secondary)]">
      {{ scope === 'workspace' ? '让助手帮你完善角色卡' : '让助手总结当前会话或提取要点' }}
    </p>
    <button v-if="!hasModel" type="button" class="btn btn-sm btn-secondary shrink-0" @click="$emit('select-model', $event)">
      选择助手模型
    </button>
  </div>
</template>

<style scoped>
.assistant-empty-state--workspace { padding-block: 3rem; }

@media (max-height: 40rem) and (min-width: 43rem) {
  .assistant-empty-state--workspace {
    flex-direction: row;
    justify-content: center;
    gap: 0.5rem;
    padding-block: 0;
  }
  .assistant-empty-icon { width: 1.75rem; height: 1.75rem; flex-shrink: 0; }
  .assistant-empty-icon svg { width: 1rem; height: 1rem; }
}
</style>
