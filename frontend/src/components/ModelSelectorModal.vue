<script setup lang="ts">
/**
 * ModelSelectorModal - 模型选择器
 * 风格：Obsidian Brutalist
 */
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  show: boolean
  models: string[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'confirm', selected: string[]): void
}>()

const searchQuery = ref('')
const selectedModels = ref<Set<string>>(new Set())

watch(() => props.show, (val) => { if (val) { searchQuery.value = ''; selectedModels.value = new Set() } })

const filteredModels = computed(() => {
  if (!searchQuery.value) return props.models
  const q = searchQuery.value.toLowerCase()
  return props.models.filter(m => m.toLowerCase().includes(q))
})

function toggle(m: string) {
  if (selectedModels.value.has(m)) selectedModels.value.delete(m)
  else selectedModels.value.add(m)
}

function confirm() {
  emit('confirm', Array.from(selectedModels.value))
  emit('update:show', false)
}
</script>

<template>
  <div v-if="show" class="modal-overlay">
    <div class="modal-backdrop" @click="emit('update:show', false)"></div>
    <div class="modal-container max-w-2xl h-[80vh]">
      <div class="modal-header">
        <h3 class="modal-title">Engine Pulse Scanner</h3>
        <button class="modal-close" @click="emit('update:show', false)">✕</button>
      </div>

      <div class="modal-content flex flex-col h-full overflow-hidden p-8 space-y-6">
        <input v-model="searchQuery" placeholder="FILTER ENGINE NODES..." class="input text-xl font-black uppercase" />

        <div class="flex items-center justify-between">
          <span class="text-[9px] font-black text-text-muted uppercase tracking-widest">
            Total: {{ props.models.length }} // Filtered: {{ filteredModels.length }}
          </span>
          <div class="flex gap-4">
            <button class="text-[9px] font-black text-brand underline" @click="filteredModels.forEach(m => selectedModels.add(m))">SELECT ALL</button>
            <button class="text-[9px] font-black text-text-muted underline" @click="filteredModels.forEach(m => selectedModels.delete(m))">CLEAR ALL</button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto custom-scrollbar border border-strong bg-dark-surface p-2">
          <div v-if="loading" class="flex flex-col items-center justify-center h-full gap-4">
            <div class="w-8 h-8 border-4 border-brand border-t-transparent animate-spin"></div>
            <span class="text-[10px] font-black text-brand uppercase tracking-widest">Scanning Network...</span>
          </div>
          <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-1">
            <div 
              v-for="m in filteredModels" 
              :key="m"
              class="flex items-center gap-4 px-4 py-3 border border-transparent hover:border-brand cursor-pointer transition-all"
              :class="selectedModels.has(m) ? 'bg-brand/10 border-brand' : 'bg-dark-bg'"
              @click="toggle(m)"
            >
              <div class="w-3 h-3 border border-strong" :class="selectedModels.has(m) ? 'bg-brand' : ''"></div>
              <span class="text-[10px] font-bold uppercase tracking-tight" :class="selectedModels.has(m) ? 'text-brand' : 'text-text-secondary'">{{ m }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <span class="text-[10px] font-black text-brand mr-auto">{{ selectedModels.size }} NODES CACHED</span>
        <button class="btn btn-secondary text-[10px] px-8" @click="emit('update:show', false)">ABORT</button>
        <button class="btn btn-primary text-[10px] px-12" @click="confirm">CONFIRM LINK</button>
      </div>
    </div>
  </div>
</template>
